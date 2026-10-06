"""Prueba el doble del puerto de generación de distractores.

`ScriptedDistractorGenerator`, en `doubles.py`, sustituye al adaptador en los
tests de quien use el puerto: entrega resultados preparados y anota qué se le
pidió, sin modelo ni red.

Este módulo no importa nada de `vocab.adapters`.
"""

from dataclasses import replace

import pytest
from tests.unit.doubles import ScriptedDistractorGenerator

from vocab.domain.cleaning import CleanSentence
from vocab.ports.distractor_generator import (
    DistractorGenerator,
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedAnswer,
    MalformedOutput,
)

REQUEST = DistractorRequest(
    term="craved",
    lemma="crave",
    pos="VERB",
    sentence=CleanSentence("All afternoon she craved something sweet."),
    definition="have an urgent desire for",
    lang="en",
)


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
    retry = replace(REQUEST, retry=MalformedAnswer(malformed.value.reason))

    assert generator.generate(retry) == generated
    assert scripted.requests == [REQUEST, REQUEST, retry]
    assert scripted.requests[2].retry == MalformedAnswer(
        "la salida trae dos distractores, no tres"
    )
