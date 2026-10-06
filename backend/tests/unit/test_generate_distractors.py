"""Prueba el caso de uso `generate_distractors` con el doble del generador: sin
modelo ni red, y con el validador real del dominio.

Este módulo no importa nada de `vocab.adapters`.
"""

from dataclasses import replace

import pytest
from tests.unit.doubles import ScriptedDistractorGenerator

from vocab.application.generate_distractors import (
    MAX_RETRIES,
    Accepted,
    AcceptedAttempt,
    Degraded,
    MalformedAttempt,
    ProviderUnavailable,
    RejectedAttempt,
    RetriesExhausted,
    UnavailableAttempt,
    generate_distractors,
)
from vocab.domain.cleaning import CleanSentence
from vocab.domain.distractor_validation import Violation, ViolationCode
from vocab.ports.distractor_generator import (
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedAnswer,
    MalformedOutput,
    RejectedDistractors,
)

REQUEST = DistractorRequest(
    term="craved",
    lemma="crave",
    pos="VERB",
    sentence=CleanSentence("All afternoon she craved something sweet."),
    definition="have an urgent desire for",
    lang="en",
)


def _generated(*distractors: str) -> GeneratedDistractors:
    first, second, third = distractors
    return GeneratedDistractors(
        distractors=(first, second, third), model="scripted", prompt_version="test"
    )


VALID = _generated("refuse to eat", "cook slowly over a low heat", "speak quietly")
# El segundo niega y la definición correcta no: D7.
WITH_NEGATION = _generated("refuse to eat", "not want anything", "speak quietly")
NEGATION_AT_1 = (Violation(ViolationCode.NEGATION, 1),)
# El tercero repite al primero salvo mayúsculas y puntuación.
WITH_DUPLICATE = _generated("refuse to eat", "speak quietly", "Refuse to eat.")
DUPLICATE_AT_2 = (Violation(ViolationCode.DUPLICATE, 2),)


def test_accepted_at_first_attempt_makes_a_single_call():
    scripted = ScriptedDistractorGenerator([VALID])

    result = generate_distractors(REQUEST, scripted)

    assert result == Accepted(VALID, (AcceptedAttempt(),))
    assert scripted.requests == [REQUEST]
    assert len(result.attempts) == len(scripted.requests)


def test_violations_then_accepted_retries_with_the_rejected_distractors():
    scripted = ScriptedDistractorGenerator([WITH_NEGATION, VALID])

    result = generate_distractors(REQUEST, scripted)

    assert result == Accepted(
        VALID,
        (
            RejectedAttempt(WITH_NEGATION.distractors, NEGATION_AT_1),
            AcceptedAttempt(),
        ),
    )
    assert len(result.attempts) == len(scripted.requests)
    assert scripted.requests == [
        REQUEST,
        replace(
            REQUEST,
            retry=RejectedDistractors(WITH_NEGATION.distractors, NEGATION_AT_1),
        ),
    ]


def test_malformed_then_accepted_retries_with_the_reason():
    reason = "la salida trae dos distractores, no tres"
    scripted = ScriptedDistractorGenerator([MalformedOutput(reason), VALID])

    result = generate_distractors(REQUEST, scripted)

    assert result == Accepted(VALID, (MalformedAttempt(reason), AcceptedAttempt()))
    assert len(result.attempts) == len(scripted.requests)
    assert scripted.requests == [
        REQUEST,
        replace(REQUEST, retry=MalformedAnswer(reason)),
    ]


def test_three_failures_degrade_after_exactly_three_calls():
    """Cada reintento lleva solo el motivo del último fallo, no los anteriores.
    El cuarto resultado del guion sobra a propósito: si se pidiera, el bucle
    habría reintentado de más."""
    reason = "la salida no es JSON"
    scripted = ScriptedDistractorGenerator(
        [WITH_NEGATION, MalformedOutput(reason), WITH_DUPLICATE, VALID]
    )

    result = generate_distractors(REQUEST, scripted)

    assert result == Degraded(
        RetriesExhausted(),
        (
            RejectedAttempt(WITH_NEGATION.distractors, NEGATION_AT_1),
            MalformedAttempt(reason),
            RejectedAttempt(WITH_DUPLICATE.distractors, DUPLICATE_AT_2),
        ),
    )
    assert len(scripted.requests) == 1 + MAX_RETRIES == 3
    assert len(result.attempts) == len(scripted.requests)
    assert scripted.requests[1].retry == RejectedDistractors(
        WITH_NEGATION.distractors, NEGATION_AT_1
    )
    assert scripted.requests[2].retry == MalformedAnswer(reason)


def test_unavailable_at_first_attempt_degrades_without_another_call():
    reason = "el proveedor no tiene el modelo configurado"
    scripted = ScriptedDistractorGenerator([GeneratorUnavailable(reason), VALID])

    result = generate_distractors(REQUEST, scripted)

    assert result == Degraded(
        ProviderUnavailable(reason), (UnavailableAttempt(reason),)
    )
    assert scripted.requests == [REQUEST]
    assert len(result.attempts) == len(scripted.requests)


def test_unavailable_in_a_retry_degrades_without_another_call():
    reason = "tiempo de espera agotado"
    scripted = ScriptedDistractorGenerator(
        [WITH_NEGATION, GeneratorUnavailable(reason), VALID]
    )

    result = generate_distractors(REQUEST, scripted)

    assert result == Degraded(
        ProviderUnavailable(reason),
        (
            RejectedAttempt(WITH_NEGATION.distractors, NEGATION_AT_1),
            UnavailableAttempt(reason),
        ),
    )
    assert len(scripted.requests) == 2
    assert len(result.attempts) == len(scripted.requests)


@pytest.mark.parametrize(
    "request_with_bad_data",
    [
        pytest.param(replace(REQUEST, lang="es"), id="language-without-markers"),
        pytest.param(replace(REQUEST, definition="…"), id="empty-definition"),
    ],
)
def test_validator_value_error_propagates(request_with_bad_data):
    """Un error de datos o de configuración no es un fallo del modelo: no se
    reintenta ni se degrada. No hay resultado del que contar intentos, así que
    se comprueban las llamadas."""
    scripted = ScriptedDistractorGenerator([VALID, VALID, VALID])

    with pytest.raises(ValueError):
        generate_distractors(request_with_bad_data, scripted)
    assert len(scripted.requests) == 1
