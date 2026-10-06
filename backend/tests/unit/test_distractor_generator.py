"""Prueba el doble del puerto de generación de distractores.

`ScriptedDistractorGenerator` sustituye al adaptador en los tests de quien use
el puerto: entrega resultados preparados y anota qué se le pidió, sin modelo ni
red.

Este módulo no importa nada de `vocab.adapters`.
"""

from collections import deque
from collections.abc import Iterable
from dataclasses import replace

import pytest

from vocab.domain.cleaning import CleanSentence
from vocab.ports.distractor_generator import (
    DistractorGenerator,
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedOutput,
)

# Lo que puede entregar el doble: un resultado o una de las dos excepciones del
# puerto. Ninguna otra, porque el puerto no promete otra.
Outcome = GeneratedDistractors | GeneratorUnavailable | MalformedOutput

REQUEST = DistractorRequest(
    term="craved",
    lemma="crave",
    pos="VERB",
    sentence=CleanSentence("All afternoon she craved something sweet."),
    definition="have an urgent desire for",
    lang="en",
)


class ScriptedDistractorGenerator:
    """Entrega un guion de resultados en orden y guarda las peticiones.

    Cada llamada consume el siguiente resultado: si es una excepción, la lanza.
    Una llamada de más es un error del test, no del proveedor, así que no lanza
    ninguna excepción del puerto que quien llama pudiera tratar como un fallo
    normal.
    """

    def __init__(self, outcomes: Iterable[Outcome]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[DistractorRequest] = []

    def generate(self, request: DistractorRequest) -> GeneratedDistractors:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError(
                f"Guion agotado: la llamada {len(self.requests)} no tiene resultado."
            )
        outcome = self._outcomes.popleft()
        if isinstance(outcome, GeneratedDistractors):
            return outcome
        raise outcome


def test_scripted_generator_delivers_outcomes_in_order_and_records_requests() -> None:
    generated = GeneratedDistractors(
        distractors=(
            "refuse to eat",
            "cook slowly over a low heat",
            "speak in a quiet voice",
        ),
        model="scripted",
        prompt_version="test",
    )
    scripted = ScriptedDistractorGenerator(
        [
            GeneratorUnavailable("tiempo de espera agotado"),
            MalformedOutput("la salida trae dos distractores, no tres"),
            generated,
        ]
    )
    # Asignación tipada: aquí comprueba mypy que el doble cumple el puerto.
    # Python no comprueba un `Protocol` al ejecutar (D-023).
    generator: DistractorGenerator = scripted

    with pytest.raises(GeneratorUnavailable) as unavailable:
        generator.generate(REQUEST)
    assert unavailable.value.reason == "tiempo de espera agotado"

    with pytest.raises(MalformedOutput) as malformed:
        generator.generate(REQUEST)
    retry = replace(REQUEST, feedback=malformed.value.reason)

    assert generator.generate(retry) == generated
    assert scripted.requests == [REQUEST, REQUEST, retry]
    assert scripted.requests[2].feedback == "la salida trae dos distractores, no tres"
