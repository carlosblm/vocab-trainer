"""Interfaz de línea de comandos: adaptador de entrada y raíz de composición.

Es el único sitio que conoce a la vez los casos de uso y los adaptadores
concretos. Aquí se construyen el motor de Postgres, el importador de Kindle, el
normalizador de spaCy, el léxico de OEWN, el generador de distractores de
Ollama y el generador aleatorio, y se inyectan en los casos de uso, que solo
conocen los puertos. Por eso los casos de uso se prueban sin base de datos ni
spaCy ni modelo, y por eso cambiar de adaptador no los toca. El léxico solo lo
construye `import`: `study` lee la definición ya guardada (D-033). El
generador solo se construye si su tarea está configurada: sin él, `study`
funciona igual, con la plantilla (§2.4). Su precalentamiento también es de
aquí: cargar el modelo es cosa del adaptador de Ollama, no del puerto, y solo
la raíz de composición sabe qué adaptador construyó.

La sesión y el cliente HTTP también se abren y se cierran aquí: quien crea un
recurso gestiona su ciclo de vida, incluida la transacción.
"""

import random
import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import httpx
import typer
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.lexicon import LexiconNotDownloaded, OewnLexicon
from vocab.adapters.lexicon.oewn import LANG as LEXICON_LANG
from vocab.adapters.lexicon.oewn import LEXICON
from vocab.adapters.llm import OllamaDistractorGenerator
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.application.generate_distractors import (
    Attempt,
    ProviderUnavailable,
    RetriesExhausted,
)
from vocab.application.import_vocabulary import import_vocabulary
from vocab.application.next_exercise import (
    ChoiceFallback,
    ClozeExercise,
    DefinitionExercise,
    DefinitionFallback,
    DegradationCause,
    ExerciseRejected,
    GeneratorNotConfigured,
    TemplateDistractors,
    next_exercise,
)
from vocab.config import get_settings
from vocab.domain.exercises.cloze_original import whole_word
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.ports.distractor_generator import DistractorGenerator, GeneratorUnavailable

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

    Solo añade lo nuevo y nunca toca lo que ya hay (D-012). Guarda con cada
    contexto la definición que se puede enseñar, así que necesita el léxico en
    WN_DATA_DIR (D-033).
    """
    lexicon = _lexicon()
    with _engine() as engine, Session(engine) as session:
        stats = import_vocabulary(
            KindleVocabImporter(path),
            PostgresVocabularyRepository(session),
            normalize,
            lexicon,
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


def _lexicon() -> OewnLexicon:
    """El léxico de la importación, antes de abrir la base: sin él no se
    importa nada, ni siquiera a medias."""
    data_dir = get_settings().wn_data_dir
    if data_dir is None:
        typer.echo(
            "Falta WN_DATA_DIR. La importación guarda con cada contexto la "
            f"definición que da el léxico {LEXICON} (D-033). Define en .env el "
            "directorio donde está, por ejemplo WN_DATA_DIR=~/wn-data.",
            err=True,
        )
        raise typer.Exit(1)
    try:
        return OewnLexicon(data_dir)
    except LexiconNotDownloaded as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@app.command()
def study(
    write: Annotated[
        bool,
        typer.Option(
            "--write",
            help=(
                "Escribir la palabra en vez de elegirla entre cuatro opciones. "
                "Sin ejercicios de definición."
            ),
        ),
    ] = False,
) -> None:
    """Muestra ejercicios mcq_definition y cloze_original.

    Si el contexto tiene una definición que se puede enseñar, hay que elegir
    cuál de cuatro es la de la palabra en su frase (mcq_definition). Los
    distractores los genera el modelo de LLM_TASK__DISTRACTORS__*, o salen de
    la plantilla si la tarea no está configurada o el modelo no los da. Si no,
    cloze_original: por defecto, elegir la palabra entre cuatro opciones; con
    --write, escribirla, y entonces todo es cloze_original. En los de
    elección se responde con el número de la opción. Sigue hasta que cierres
    la entrada (Ctrl+D) o interrumpas (Ctrl+C). No guarda las respuestas: eso
    llega en F3.

    Al empezar, si la tarea está configurada, deja el modelo cargado en
    Ollama. Si no se puede, toda la sesión usa la plantilla, con un aviso.
    """
    rng = random.Random()
    shown = correct = 0

    with _engine() as engine, _distractor_generator(needed=not write) as generator:
        while True:
            # Una sesión por ejercicio, cerrada antes de esperar la respuesta:
            # así no queda una transacción abierta mientras piensas. Sí queda
            # abierta mientras el modelo genera, porque la plantilla, si hace
            # falta, se lee después. `study` solo lee y nunca confirma. Lo
            # único que podría escribir es el usuario que `ensure_user` crea en
            # una base vacía, y se descarta al cerrar.
            with Session(engine) as session:
                item = next_exercise(
                    PostgresVocabularyRepository(session),
                    generator,
                    rng,
                    choice=not write,
                )

            if item is None:
                typer.echo(
                    "No hay entradas en estudio con contexto utilizable. "
                    "Importa un vocab.db con `vocab import`."
                )
                return

            typer.echo("")
            if isinstance(item, DefinitionExercise):
                answered = _ask_definition(item)
            else:
                answered = _ask_cloze(item)
            if answered is None:
                break
            shown += 1
            correct += answered

    typer.echo(f"\n{correct} de {shown} correctas.")


@contextmanager
def _distractor_generator(*, needed: bool) -> Generator[DistractorGenerator | None]:
    """El generador de distractores, con el modelo ya cargado, o `None` si la
    sesión va sin modelo.

    - Sin `needed` (`--write`), `None` y nada más: esa sesión nunca genera, y
      precalentar cargaría el modelo para nada.
    - Sin la tarea configurada, `None`, con un aviso.
    - Con la tarea, el cliente HTTP se crea aquí, con la URL y el tiempo de
      espera para generar, y se cierra al terminar, como el motor. Antes del
      primer ejercicio, `warm_up` deja el modelo cargado, con el tiempo de
      espera largo, y avisa si tiene que cargarlo. Si falla, toda la sesión
      sigue sin generador, con un solo aviso al empezar: con él, cada
      ejercicio de definición volvería a esperar el mismo fallo.

    Sin modelo, el aviso sale aquí, una vez, y no en cada ejercicio de
    definición (`_ask_definition`).

    Los idiomas son el del léxico: solo los contextos con una definición
    suya, los `eligible`, piden distractores (D-033).
    """
    if not needed:
        yield None
        return
    settings = get_settings()
    task = settings.llm_task.distractors
    if task is None:
        typer.echo(
            _without_model_notice(
                "la tarea de distractores no está configurada "
                "(LLM_TASK__DISTRACTORS__*)"
            )
        )
        yield None
        return
    if settings.ollama_base_url is None:
        # La tarea está configurada y no se puede atender: es un error de
        # configuración, no una caída del proveedor, y no se degrada en
        # silencio.
        typer.echo(
            "Falta OLLAMA_BASE_URL. La tarea de distractores está configurada "
            "con el proveedor ollama (LLM_TASK__DISTRACTORS__PROVIDER). Define "
            "en .env dónde escucha, por ejemplo "
            "OLLAMA_BASE_URL=http://localhost:11434, o quita la tarea para "
            "estudiar con la plantilla.",
            err=True,
        )
        raise typer.Exit(1)
    with httpx.Client(
        base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_seconds
    ) as client:
        generator = OllamaDistractorGenerator(
            client,
            load_timeout_seconds=settings.ollama_load_timeout_seconds,
            model=task.model,
            prompt_version=task.prompt_version,
            languages=(LEXICON_LANG,),
            think=task.think,
            temperature=task.temperature,
        )
        try:
            generator.warm_up(before_loading=lambda: typer.echo("Cargando el modelo…"))
        except GeneratorUnavailable as error:
            typer.echo(_without_model_notice(error.reason))
            yield None
            return
        # Fuera del `try`: una `GeneratorUnavailable` durante la sesión no es
        # del precalentamiento, y la trata cada ejercicio.
        yield generator


def _without_model_notice(reason: str) -> str:
    """El aviso, al empezar, de una sesión sin modelo."""
    return f"Sin modelo: {reason}. Los ejercicios de definición usan la plantilla."


def _ask_cloze(item: ClozeExercise) -> bool | None:
    """Muestra un cloze_original, lee la respuesta y la corrige. `None` si se
    cerró la entrada."""
    exercise = item.exercise
    cloze = exercise.cloze if isinstance(exercise, ClozeOriginalChoice) else exercise
    if item.definition_fallback is not None:
        typer.echo(_definition_fallback_notice(item.definition_fallback))
    if item.fallback is not None:
        typer.echo(_fallback_notice(item.fallback))
    typer.echo(cloze.masked_sentence)

    if isinstance(exercise, ClozeOriginalChoice):
        for number, option in enumerate(exercise.options, start=1):
            typer.echo(f"  {number}) {option}")
        index = _ask_option(len(exercise.options))
        if index is None:
            return None
        response = exercise.options[index]
    else:
        try:
            response = typer.prompt("Respuesta", default="", show_default=False)
        except typer.Abort:
            return None

    if exercise.is_correct(response):
        typer.echo("Correcto.")
        return True
    typer.echo(f"Incorrecto. La palabra era «{cloze.word}».")
    typer.echo(f"Frase: {cloze.sentence}")
    return False


def _ask_definition(item: DefinitionExercise) -> bool | None:
    """Muestra un mcq_definition, lee la opción y la corrige por índice. Tras
    responder, acierto o no, muestra la definición correcta. `None` si se
    cerró la entrada."""
    exercise = item.exercise
    source = item.source
    # Sin modelo en toda la sesión, el aviso ya salió al empezar.
    if isinstance(source, TemplateDistractors) and not isinstance(
        source.cause, GeneratorNotConfigured
    ):
        reason = _degradation_reason(source.cause, source.attempts)
        typer.echo(f"Distractores de la plantilla: {reason}.")
    typer.echo(_highlighted(exercise.sentence, exercise.word))
    for number, option in enumerate(exercise.displayed_options, start=1):
        typer.echo(f"  {number}) {option}")

    chosen = _ask_option(len(exercise.options))
    if chosen is None:
        return None

    answer = exercise.answer_index
    is_correct = exercise.is_correct(chosen)
    typer.echo("Correcto." if is_correct else f"Incorrecto. Era la {answer + 1}.")
    typer.echo(f"Definición: {exercise.displayed_options[answer]}")
    return is_correct


def _highlighted(sentence: str, word: str) -> str:
    """La frase con todas las apariciones de la palabra entre comillas
    angulares, localizadas como en el ejercicio (D-019).

    Comillas y no color: se ven igual en cualquier terminal, y también al
    copiar la sesión o redirigir la salida, donde Click quita los colores.
    """
    return whole_word(word).sub(_quoted, sentence)


def _quoted(match: re.Match[str]) -> str:
    return f"«{match.group(0)}»"


def _ask_option(count: int) -> int | None:
    """La opción elegida, por su posición desde 0, o `None` si se cerró la
    entrada.

    Solo vale el número de una opción. Cualquier otra respuesta, también la
    vacía o la palabra escrita, vuelve a preguntar con un recordatorio, y no
    cuenta como fallo: es un error al teclear, no una respuesta.
    """
    while True:
        try:
            response = typer.prompt(
                f"Elige (1-{count})", default="", show_default=False
            )
        except typer.Abort:
            return None
        text = response.strip()
        # `isdecimal` y no `isdigit`: `²` es dígito, e `int` no lo admite.
        if text.isdecimal() and 1 <= int(text) <= count:
            return int(text) - 1
        typer.echo(f"Escribe un número del 1 al {count}.")


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


def _definition_fallback_notice(fallback: DefinitionFallback) -> str:
    """El aviso del repliegue de mcq_definition a cloze_original (§7.3)."""
    reason = _degradation_reason(fallback.cause, fallback.attempts)
    return (
        f"Sin ejercicio de definición: {reason}, y tus palabras no dan tres "
        "definiciones que sirvan de distractores."
    )


def _degradation_reason(cause: DegradationCause, attempts: tuple[Attempt, ...]) -> str:
    """Por qué los distractores no son del modelo, en una frase sin punto.

    Con el proveedor caído, el motivo del adaptador tal cual: lleva la URL y
    el modelo, que es lo que hace falta para arreglarlo (D-028).
    """
    match cause:
        case ProviderUnavailable(reason=reason):
            return reason
        case RetriesExhausted():
            return (
                f"el modelo no dio tres distractores válidos en {len(attempts)} "
                "intentos"
            )
        case GeneratorNotConfigured():
            # Por qué no hay modelo lo dijo el aviso del principio: la tarea
            # no está configurada o el precalentamiento falló.
            return "la sesión va sin modelo"
        case ExerciseRejected(reason=reason):
            return (
                "los distractores del modelo pasaron los validadores, pero no "
                f"forman un ejercicio válido ({reason})"
            )


if __name__ == "__main__":
    app()
