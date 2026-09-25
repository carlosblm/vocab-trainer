"""Interfaz de línea de comandos: adaptador de entrada y raíz de composición.

Es el único sitio que conoce a la vez los casos de uso y los adaptadores
concretos. Aquí se construyen el motor de Postgres, el importador de Kindle, el
normalizador de spaCy y el generador aleatorio, y se inyectan en los casos de
uso, que solo conocen los puertos. Por eso los casos de uso se prueban sin base
de datos ni spaCy, y por eso cambiar de adaptador no los toca.

La sesión también se abre y se cierra aquí: quien crea un recurso gestiona su
ciclo de vida, incluida la transacción.
"""

import random
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.application.import_vocabulary import import_vocabulary
from vocab.application.next_exercise import ChoiceFallback, next_exercise
from vocab.config import get_settings
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice

app = typer.Typer(
    help="Estudio de vocabulario a partir del vocab.db de Kindle.",
    no_args_is_help=True,
)


@contextmanager
def _engine() -> Generator[Engine]:
    """El motor se construye al ejecutar un comando, nunca al importar el
    módulo (D-017), y se libera al terminar."""
    engine = create_engine(get_settings().database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@app.command("import")
def import_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="Ruta al vocab.db."
        ),
    ],
) -> None:
    """Importa un vocab.db.

    Solo añade lo nuevo y nunca toca lo que ya hay (D-012).
    """
    with _engine() as engine, Session(engine) as session:
        stats = import_vocabulary(
            KindleVocabImporter(path),
            PostgresVocabularyRepository(session),
            normalize,
            filename=path.name,
        )
        # Una importación es una sola transacción: fuente, entradas y
        # contextos, o nada. Si algo falla antes de esta línea, la sesión se
        # cierra sin confirmar y Postgres lo deshace todo. Como la ingesta es
        # idempotente, basta con volver a lanzarla.
        session.commit()

    typer.echo(
        f"Entradas: {stats.entries_created} nuevas, "
        f"{stats.entries_existing} ya existían."
    )
    typer.echo(
        f"Contextos: {stats.contexts_created} nuevos, "
        f"{stats.contexts_existing} ya existían."
    )


@app.command()
def study(
    write: Annotated[
        bool,
        typer.Option(
            "--write",
            help="Escribir la palabra en vez de elegirla entre cuatro opciones.",
        ),
    ] = False,
) -> None:
    """Muestra ejercicios cloze_original.

    Por defecto hay que elegir la palabra entre cuatro opciones; con --write,
    escribirla. Sigue hasta que cierres la entrada (Ctrl+D) o interrumpas
    (Ctrl+C). No guarda las respuestas: eso llega en F3.
    """
    rng = random.Random()
    shown = correct = 0

    with _engine() as engine:
        while True:
            # Una sesión por ejercicio, cerrada antes de esperar la respuesta:
            # así no queda una transacción abierta mientras piensas. `study`
            # solo lee y nunca confirma. Lo único que podría escribir es el
            # usuario que `ensure_user` crea en una base vacía, y se descarta
            # al cerrar.
            with Session(engine) as session:
                item = next_exercise(
                    PostgresVocabularyRepository(session), rng, choice=not write
                )

            if item is None:
                typer.echo(
                    "No hay entradas en estudio con contexto utilizable. "
                    "Importa un vocab.db con `vocab import`."
                )
                return

            exercise = item.exercise
            cloze = (
                exercise.cloze
                if isinstance(exercise, ClozeOriginalChoice)
                else exercise
            )
            typer.echo("")
            if item.fallback is not None:
                typer.echo(_fallback_notice(item.fallback))
            typer.echo(cloze.masked_sentence)
            if isinstance(exercise, ClozeOriginalChoice):
                for number, option in enumerate(exercise.options, start=1):
                    typer.echo(f"  {number}) {option}")

            label = (
                "Elige (1-4)"
                if isinstance(exercise, ClozeOriginalChoice)
                else "Respuesta"
            )
            try:
                response = typer.prompt(label, default="", show_default=False)
            except typer.Abort:
                break
            if isinstance(exercise, ClozeOriginalChoice):
                response = _chosen_option(exercise, response)

            shown += 1
            if exercise.is_correct(response):
                correct += 1
                typer.echo("Correcto.")
            else:
                typer.echo(f"Incorrecto. La palabra era «{cloze.word}».")
                typer.echo(f"Frase: {cloze.sentence}")

    typer.echo(f"\n{correct} de {shown} correctas.")


def _chosen_option(exercise: ClozeOriginalChoice, response: str) -> str:
    """El número de una opción la elige; cualquier otra cosa se corrige como
    si se hubiera escrito."""
    text = response.strip()
    if text.isdigit() and 1 <= int(text) <= len(exercise.options):
        return exercise.options[int(text) - 1]
    return response


def _fallback_notice(fallback: ChoiceFallback) -> str:
    """El aviso del repliegue a escritura, con su motivo (D-022)."""
    if fallback.pos is None:
        reason = (
            "spaCy no localizó la palabra en su frase, así que no se sabe qué "
            "forma gramatical deberían tener las opciones"
        )
    else:
        form = f"{fallback.pos} {fallback.morph or 'sin rasgos'}"
        if fallback.available == 0:
            others = "ninguna otra de tus palabras consultadas tiene"
        elif fallback.available == 1:
            others = "solo otra de tus palabras consultadas tiene"
        else:
            others = (
                f"solo otras {fallback.available} de tus palabras consultadas tienen"
            )
        reason = (
            f"{others} su misma forma gramatical ({form}), y hacen falta "
            f"{fallback.needed} para que la gramática no delate la respuesta"
        )
    return f"Sin opciones: {reason}. Escríbela."


if __name__ == "__main__":
    app()
