"""Caso de uso: obtener el siguiente ejercicio de estudio.

Hasta F3 el selector es el azar, no FSRS: se elige una entrada y, dentro de
ella, uno de sus contextos utilizables. No se persiste nada: las respuestas y
el estado de repaso llegan en F3.

Qué ejercicio sale lo decide el contexto elegido. Si su definición es
`eligible` (D-033), `mcq_definition`, con los distractores del modelo o, si la
generación degrada, de la plantilla (§7.3). Si no, `cloze_original` (D-022).
Cuándo pasar de opción múltiple a escritura es de F3, con FSRS.

El corpus se lee en cada llamada, no una vez por sesión. El caso de uso no
guarda estado, que es lo que pedirá F3: una API sin estado en el proceso
(§3.3.3), donde cada petición es independiente. Y lo que se lee está siempre al
día: en F3 responder cambiará el estado de repaso y las entradas `known`, y una
copia en memoria habría que invalidarla. Con el volumen actual el coste es
despreciable, así que no hay nada que optimizar.

No imprime nada (D-028): lo que haya que avisar viaja en el resultado, como
datos, y lo redacta quien lo muestra.
"""

import logging
import random
from dataclasses import dataclass, replace

from vocab.application.generate_distractors import (
    Accepted,
    Attempt,
    ProviderUnavailable,
    RetriesExhausted,
    generate_distractors,
)
from vocab.domain.cleaning import CleanSentence
from vocab.domain.definition_policy import DefinitionStatus
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import (
    OPTION_COUNT,
    ClozeOriginalChoice,
)
from vocab.domain.exercises.definition_template import choose_template_distractors
from vocab.domain.exercises.distractors import choose_options, eligible_forms
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import Context, Entry
from vocab.ports.distractor_generator import (
    DistractorGenerator,
    DistractorRequest,
    GeneratedDistractors,
)
from vocab.ports.repository import StudyRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChoiceFallback:
    """Por qué un ejercicio que debía ser de elección se presenta para escribir.

    Los datos, no el mensaje: redactarlo es cosa de quien lo muestra.
    `pos = None` significa que la respuesta no tiene análisis y no hay forma
    gramatical que igualar; si no, había `available` distractores posibles y
    hacían falta `needed`.
    """

    pos: str | None
    morph: str | None
    available: int
    needed: int


@dataclass(frozen=True)
class GeneratorNotConfigured:
    """No hay generador de distractores: su tarea no está configurada. `study`
    sigue funcionando sin ningún modelo (§2.4), con la plantilla."""


@dataclass(frozen=True)
class ExerciseRejected:
    """El modelo dio distractores que pasaron los validadores, pero
    `McqDefinition` no los admitió.

    No debería ocurrir: los validadores comprueban lo mismo que las
    invariantes del ejercicio. Si ocurre, tienen un hueco, y esto es la
    evidencia: `reason` es el del `ValueError`, y `generated`, lo que devolvió
    el generador, con el modelo y el prompt que lo produjeron.
    """

    reason: str
    generated: GeneratedDistractors


# Por qué los distractores de un `mcq_definition` no son del modelo. Las dos
# primeras son las de `generate_distractors`; las otras dos, de este caso de
# uso.
DegradationCause = (
    ProviderUnavailable | RetriesExhausted | GeneratorNotConfigured | ExerciseRejected
)


@dataclass(frozen=True)
class ModelDistractors:
    """Los distractores son del modelo (A1): la configuración que los produjo y
    los intentos que costaron. Es lo que guardará con el ejercicio la
    persistencia (§3.3.4, regla 4)."""

    model: str
    prompt_version: str
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True)
class TemplateDistractors:
    """Los distractores son de la plantilla (§7.3), porque la generación
    degradó por `cause`.

    `attempts` son los intentos del modelo antes de degradar: vacío si no hay
    generador, y con un último `AcceptedAttempt` si fue `ExerciseRejected`.
    """

    cause: DegradationCause
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True)
class DefinitionFallback:
    """Por qué un contexto `eligible` se presenta como `cloze_original`: la
    generación degradó por `cause` y la plantilla no encontró tres
    distractores. Los mismos datos que `TemplateDistractors`, pero sin
    plantilla."""

    cause: DegradationCause
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True)
class DefinitionExercise:
    """Un `mcq_definition` y de dónde salieron sus distractores."""

    exercise: McqDefinition
    source: ModelDistractors | TemplateDistractors


@dataclass(frozen=True)
class ClozeExercise:
    """Un `cloze_original` y, si hubo repliegue, sus motivos: de elección a
    escritura (`fallback`, D-022) y de `mcq_definition` a `cloze_original`
    (`definition_fallback`). Pueden darse los dos."""

    exercise: ClozeOriginal | ClozeOriginalChoice
    fallback: ChoiceFallback | None = None
    definition_fallback: DefinitionFallback | None = None


# Una unión y no un tipo con campos opcionales: así no se puede construir un
# `mcq_definition` sin la procedencia de sus distractores, y quien muestra el
# ejercicio tiene que tratar los dos casos para que mypy lo acepte.
NextExercise = DefinitionExercise | ClozeExercise


def next_exercise(
    repository: StudyRepository,
    generator: DistractorGenerator | None,
    rng: random.Random,
    *,
    choice: bool,
) -> NextExercise | None:
    """Un ejercicio al azar, o `None` si no hay nada que estudiar.

    Con `choice`, el contexto elegido decide el ejercicio: `mcq_definition` si
    es `eligible` (ver `_definition_exercise`) y, si no, la variante de
    elección de `cloze_original` (D-022). Si ese contexto no tiene tres
    distractores, se presenta para escribir y se dice por qué: no se busca
    otro contexto que sí los tenga, porque eso sesgaría la selección hacia las
    palabras con muchas formas parecidas.

    Sin `choice`, siempre `cloze_original` para escribir: `mcq_definition` es
    de opción múltiple y no tiene variante de escritura, así que con `--write`
    no se llama al generador.

    `generator` es `None` si la tarea de distractores no está configurada: los
    contextos `eligible` van entonces a la plantilla, y el resultado lo dice.

    `rng` entra por parámetro: la CLI pasa uno sin semilla y los tests uno con
    semilla, así que el resultado de un test es siempre el mismo.

    Un contexto cuya palabra no aparece como palabra completa no admite
    ejercicio (`ClozeOriginal` lanza `ValueError`): se avisa y se prueba otro
    contexto de la misma entrada y, si no queda ninguno, otra entrada. Con la
    palabra de cada contexto ocurre en 0 de los 999 contextos de la exportación
    de septiembre de 2026, así que es una red de seguridad. Si no la hubiera, un
    solo dato malo dejaría inservible el comando entero. `McqDefinition` tiene
    la misma invariante, así que un contexto que pasa aquí también la cumple.

    Por eso se recorren permutaciones aleatorias en lugar de llamar a `choice`
    una vez: la primera entrada válida de una permutación al azar es uniforme
    entre las válidas, igual que un `choice` sobre ellas, y el bucle termina
    siempre. Reintentar `choice` podría repetir la misma entrada rota.
    """
    user_id = repository.ensure_user()
    entries = repository.list_learning_entries_with_usable_context(user_id)
    # Los candidatos solo hacen falta para la variante de elección.
    candidates = repository.list_non_noise_entries(user_id) if choice else []
    for entry in rng.sample(entries, k=len(entries)):
        contexts = entry.usable_contexts
        for context in rng.sample(contexts, k=len(contexts)):
            try:
                # La palabra es la del contexto, no `entry.term`: con la de la
                # entrada fallan 49 de esos 999 contextos (D-020).
                cloze = ClozeOriginal(
                    sentence=context.clean_sentence, word=context.term
                )
            except ValueError as error:
                logger.warning(
                    "contexto %s sin ejercicio: %s", context.external_id, error
                )
                continue
            if not choice:
                return ClozeExercise(cloze)
            definition = _eligible_definition(context)
            if definition is None:
                return _with_options(cloze, entry, context, candidates, rng)
            outcome = _definition_exercise(
                entry, context, definition, generator, repository, user_id, rng
            )
            if isinstance(outcome, DefinitionExercise):
                return outcome
            return replace(
                _with_options(cloze, entry, context, candidates, rng),
                definition_fallback=outcome,
            )
    return None


def _eligible_definition(context: Context) -> str | None:
    """La definición que se puede enseñar, si el contexto es `eligible`."""
    decision = context.definition
    if decision is None or decision.status is not DefinitionStatus.ELIGIBLE:
        return None
    return decision.definition


def _definition_exercise(
    entry: Entry,
    context: Context,
    definition: str,
    generator: DistractorGenerator | None,
    repository: StudyRepository,
    user_id: int,
    rng: random.Random,
) -> DefinitionExercise | DefinitionFallback:
    """El `mcq_definition` del contexto, con los distractores del modelo o, si
    la generación degrada, con los de la plantilla. Si la plantilla tampoco
    tiene tres, el motivo del repliegue a `cloze_original`.

    Los candidatos de la plantilla se leen solo si hacen falta: con el modelo
    respondiendo, no se usan.
    """
    from_model = _from_model(entry, context, definition, generator, rng)
    if isinstance(from_model, DefinitionExercise):
        return from_model
    template = choose_template_distractors(
        entry, context, repository.list_definition_candidates(user_id), rng
    )
    if template is None:
        return DefinitionFallback(from_model.cause, from_model.attempts)
    # Sin red de seguridad, al revés que con los del modelo: la plantilla
    # sale de datos propios y validados, y sobre la exportación de septiembre
    # de 2026 forma ejercicio en los 270 contextos `eligible` de `study`. Un
    # `ValueError` aquí es un error del código, y tiene que verse.
    exercise = McqDefinition.new(
        context.clean_sentence, context.term, definition, template, rng
    )
    return DefinitionExercise(exercise, from_model)


def _from_model(
    entry: Entry,
    context: Context,
    definition: str,
    generator: DistractorGenerator | None,
    rng: random.Random,
) -> DefinitionExercise | TemplateDistractors:
    """El ejercicio con los distractores del modelo o, si no los hay, por qué
    tocan los de la plantilla."""
    if generator is None:
        return TemplateDistractors(GeneratorNotConfigured(), attempts=())
    assert context.pos is not None, "un contexto eligible tiene categoría (D-025)"
    request = DistractorRequest(
        term=context.term,
        lemma=entry.lemma,
        pos=context.pos,
        # Vuelve de Postgres como `str`; ya es la frase limpia.
        sentence=CleanSentence(context.clean_sentence),
        definition=definition,
        lang=entry.lang,
    )
    # Fuera del `try`: un `ValueError` de la generación (idioma sin prompt o
    # sin marcadores) es de configuración y no se captura (D-028).
    result = generate_distractors(request, generator)
    if not isinstance(result, Accepted):
        return TemplateDistractors(result.cause, result.attempts)
    generated = result.distractors
    try:
        exercise = McqDefinition.new(
            context.clean_sentence,
            context.term,
            definition,
            generated.distractors,
            rng,
        )
    except ValueError as error:
        # Lo que el modelo devuelve es una entrada externa: si los
        # validadores dejaran pasar algo que el ejercicio no admite, la sesión
        # no debe caerse por eso.
        return TemplateDistractors(
            ExerciseRejected(str(error), generated), result.attempts
        )
    return DefinitionExercise(
        exercise,
        ModelDistractors(generated.model, generated.prompt_version, result.attempts),
    )


def _with_options(
    cloze: ClozeOriginal,
    entry: Entry,
    context: Context,
    candidates: list[Entry],
    rng: random.Random,
) -> ClozeExercise:
    options = choose_options(entry, context, candidates, rng)
    if options is None:
        return ClozeExercise(
            cloze,
            fallback=ChoiceFallback(
                pos=context.pos,
                morph=context.morph,
                available=len(eligible_forms(entry, context, candidates)),
                needed=OPTION_COUNT - 1,
            ),
        )
    return ClozeExercise(ClozeOriginalChoice(cloze=cloze, options=options))
