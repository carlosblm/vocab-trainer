"""Caso de uso: obtener el siguiente ejercicio de estudio.

Hasta F3 el selector es el azar, no FSRS: se elige una entrada y, dentro de
ella, uno de sus contextos utilizables. No se persiste nada: las respuestas y
el estado de repaso llegan en F3.
"""

import logging
import random

from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.ports.repository import StudyRepository

logger = logging.getLogger(__name__)


def next_exercise(
    repository: StudyRepository, rng: random.Random
) -> ClozeOriginal | None:
    """Un ejercicio al azar, o `None` si no hay nada que estudiar.

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
    for entry in rng.sample(entries, k=len(entries)):
        contexts = entry.usable_contexts
        for context in rng.sample(contexts, k=len(contexts)):
            try:
                # La palabra es la del contexto, no `entry.term`: con la de la
                # entrada fallan 49 de esos 999 contextos (D-020).
                return ClozeOriginal(sentence=context.clean_sentence, word=context.term)
            except ValueError as error:
                logger.warning(
                    "contexto %s sin ejercicio: %s", context.external_id, error
                )
    return None
