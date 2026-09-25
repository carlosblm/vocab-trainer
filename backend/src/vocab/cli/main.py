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
from vocab.application.next_exercise import next_exercise
from vocab.config import get_settings

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
def study() -> None:
    """Muestra ejercicios cloze_original.

    Sigue hasta que cierres la entrada (Ctrl+D) o interrumpas (Ctrl+C). No
    guarda las respuestas: eso llega en F3.
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
                exercise = next_exercise(PostgresVocabularyRepository(session), rng)

            if exercise is None:
                typer.echo(
                    "No hay entradas en estudio con contexto utilizable. "
                    "Importa un vocab.db con `vocab import`."
                )
                return

            typer.echo(f"\n{exercise.masked_sentence}")
            try:
                response = typer.prompt("Respuesta", default="", show_default=False)
            except typer.Abort:
                break

            shown += 1
            if exercise.is_correct(response):
                correct += 1
                typer.echo("Correcto.")
            else:
                typer.echo(f"Incorrecto. La palabra era «{exercise.word}».")
                typer.echo(f"Frase: {exercise.sentence}")

    typer.echo(f"\n{correct} de {shown} correctas.")


if __name__ == "__main__":
    app()
