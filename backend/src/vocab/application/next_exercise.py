"""Caso de uso: obtener el siguiente ejercicio de estudio.

Hasta F3 el selector es el azar, no FSRS: se elige una entrada y, dentro de
ella, uno de sus contextos utilizables. No se persiste nada: las respuestas y
el estado de repaso llegan en F3.

El corpus se lee en cada llamada, no una vez por sesión. El caso de uso no
guarda estado, que es lo que pedirá F3: una API sin estado en el proceso
(§3.3.3), donde cada petición es independiente. Y lo que se lee está siempre al
día: en F3 responder cambiará el estado de repaso y las entradas `known`, y una
copia en memoria habría que invalidarla. Con el volumen actual el coste es
despreciable, así que no hay nada que optimizar.
"""

import logging
import random
from dataclasses import dataclass

from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import (
    OPTION_COUNT,
    ClozeOriginalChoice,
)
from vocab.domain.exercises.distractors import choose_options, eligible_forms
from vocab.domain.models import Context, Entry
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
class NextExercise:
    """El ejercicio que toca y, si hubo repliegue a escritura, su motivo."""

    exercise: ClozeOriginal | ClozeOriginalChoice
    fallback: ChoiceFallback | None = None


def next_exercise(
    repository: StudyRepository, rng: random.Random, *, choice: bool
) -> NextExercise | None:
    """Un ejercicio al azar, o `None` si no hay nada que estudiar.

    Con `choice`, variante de elección (D-022). Si el contexto elegido no tiene
    tres distractores, se presenta ese mismo contexto para escribir y se dice
    por qué: no se busca otro contexto que sí los tenga, porque eso sesgaría la
    selección hacia las palabras con muchas formas parecidas.

    `rng` entra por parámetro: la CLI pasa uno sin semilla y los tests uno con
    semilla, así que el resultado de un test es siempre el mismo.

    Un contexto cuya palabra no aparece como palabra completa no admite
    ejercicio (`ClozeOriginal` lanza `ValueError`): se avisa y se prueba otro
    contexto de la misma entrada y, si no queda ninguno, otra entrada. Con la
    palabra de cada contexto ocurre en 0 de los 999 contextos de la exportación
    de septiembre de 2026, así que es una red de seguridad. Si no la hubiera, un
    solo dato malo dejaría inservible el comando entero.

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
                return NextExercise(cloze)
            return _with_options(cloze, entry, context, candidates, rng)
    return None


def _with_options(
    cloze: ClozeOriginal,
    entry: Entry,
    context: Context,
    candidates: list[Entry],
    rng: random.Random,
) -> NextExercise:
    options = choose_options(entry, context, candidates, rng)
    if options is None:
        return NextExercise(
            cloze,
            fallback=ChoiceFallback(
                pos=context.pos,
                morph=context.morph,
                available=len(eligible_forms(entry, context, candidates)),
                needed=OPTION_COUNT - 1,
            ),
        )
    return NextExercise(ClozeOriginalChoice(cloze=cloze, options=options))
