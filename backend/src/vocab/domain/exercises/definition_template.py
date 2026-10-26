"""Plantilla de degradación de `mcq_definition` (§7.3): tres distractores
tomados de las definiciones del propio vocabulario, sin modelo.

Es el camino cuando el generador no está disponible o agota sus reintentos
(D-028). Peor pedagógicamente que A1, pero siempre funcional y determinista
con una semilla.

Función pura, como `choose_options` (D-022): los candidatos y el azar entran
por parámetro, y el resultado son tres distractores o `None`. Con `None`, el
ejercicio es `cloze_original`.
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass

from vocab.domain.definition_policy import DefinitionStatus
from vocab.domain.distractor_validation import validate_distractors
from vocab.domain.models import Context, Entry

# Los distractores de una `mcq_definition`: cuatro opciones menos la correcta.
DISTRACTOR_COUNT = 3


@dataclass(frozen=True)
class DefinitionCandidate:
    """Una definición segura del vocabulario: la de un contexto `eligible` de
    una entrada que no es `noise` (D-033).

    Lleva lo que hace falta para decidir si sirve de distractor: el lema y el
    idioma de su entrada, la categoría de su contexto y su sentido.
    """

    lemma: str
    lang: str
    pos: str
    sense_id: str
    definition: str


def choose_template_distractors(
    entry: Entry,
    context: Context,
    candidates: Iterable[DefinitionCandidate],
    rng: random.Random,
) -> tuple[str, str, str] | None:
    """Tres definiciones de otras palabras que sirven de distractores de la de
    `context`, o `None` si no hay tres.

    Un candidato vale si es del mismo idioma y la misma categoría (si no, la
    gramática de la definición delata la respuesta), de otro lema (sería otra
    definición correcta) y de otro sentido, y si su sentido no se repite.

    Los tres, además, pasan `validate_distractors` (básico, D1 y D7). Se
    recorren en un orden al azar y se descartan los que una violación señala:
    un vacío, una negación o el que contiene la correcta no sirven con ningún
    otro, y de dos con las mismas palabras se queda el primero. Así, `None`
    significa que no existen tres válidos, no que el azar no los encontrara.

    `context` tiene que ser `eligible`: si no, no hay definición correcta de la
    que distraer, y se lanza `ValueError`.
    """
    decision = context.definition
    if decision is None or decision.status is not DefinitionStatus.ELIGIBLE:
        raise ValueError("la plantilla necesita un contexto eligible")
    assert decision.definition is not None and decision.sense_id is not None, (
        "DefinitionDecision garantiza definición y sentido con eligible"
    )

    pool = _candidate_pool(entry, context.pos, decision.sense_id, candidates)
    rng.shuffle(pool)

    chosen: list[str] = []
    for definition in pool:
        chosen.append(definition)
        if len(chosen) < DISTRACTOR_COUNT:
            continue
        first, second, third = chosen
        violations = validate_distractors(
            decision.definition, (first, second, third), entry.lang
        )
        if not violations:
            return (first, second, third)
        rejected = {violation.distractor_index for violation in violations}
        chosen = [item for index, item in enumerate(chosen) if index not in rejected]
    return None


def _candidate_pool(
    entry: Entry,
    pos: str | None,
    sense_id: str,
    candidates: Iterable[DefinitionCandidate],
) -> list[str]:
    """Las definiciones de los candidatos que valen, en el orden de llegada y
    con un solo representante por sentido."""
    seen = {sense_id}
    pool: list[str] = []
    for candidate in candidates:
        if (
            candidate.lang != entry.lang
            or candidate.pos != pos
            or candidate.lemma == entry.lemma
            or candidate.sense_id in seen
        ):
            continue
        seen.add(candidate.sense_id)
        pool.append(candidate.definition)
    return pool
