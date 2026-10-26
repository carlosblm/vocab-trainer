"""Prueba el ejercicio `mcq_definition`: orden fijo con semilla, corrección por
índice, invariantes y el estilo con que se muestran las opciones."""

import random

import pytest

from vocab.domain.exercises.mcq_definition import McqDefinition, displayed

SENTENCE = "They sojourned in the mountains for a month."
WORD = "sojourned"
DEFINITION = "spend a certain length of time; reside temporarily"
DISTRACTORS = (
    "travel quickly from one place to another",
    "speak in a low and quiet voice",
    "work hard for a long period of time",
)


def _exercise(seed: int) -> McqDefinition:
    return McqDefinition.new(
        SENTENCE, WORD, DEFINITION, DISTRACTORS, random.Random(seed)
    )


# Orden y corrección.


def test_same_seed_gives_the_same_order() -> None:
    assert _exercise(7).options == _exercise(7).options


def test_options_are_the_definition_and_the_distractors() -> None:
    exercise = _exercise(7)

    assert sorted(exercise.options) == sorted((DEFINITION, *DISTRACTORS))
    assert exercise.options[exercise.answer_index] == DEFINITION
    assert sorted(exercise.distractors) == sorted(DISTRACTORS)


def test_order_depends_on_the_random_source() -> None:
    """Con semillas distintas la correcta no queda siempre en el mismo sitio:
    si no, la posición delataría la respuesta."""
    positions = {_exercise(seed).answer_index for seed in range(20)}

    assert len(positions) > 1


def test_correction_is_by_index() -> None:
    exercise = _exercise(7)

    assert exercise.is_correct(exercise.answer_index)
    others = [index for index in range(4) if index != exercise.answer_index]
    assert not any(exercise.is_correct(index) for index in others)
    assert not exercise.is_correct(4)


# Invariantes.


@pytest.mark.parametrize("count", [3, 5])
def test_four_options_are_required(count: int) -> None:
    options = (DEFINITION, *DISTRACTORS, "eat something sweet")[:count]

    with pytest.raises(ValueError, match="4 opciones"):
        McqDefinition(SENTENCE, WORD, DEFINITION, options)


def test_options_repeated_by_words_are_rejected() -> None:
    """Las mismas palabras con otra mayúscula y otra puntuación son la misma
    opción: se compara como los validadores (D-027)."""
    options = (
        DEFINITION,
        DISTRACTORS[0],
        DISTRACTORS[1],
        "Travel quickly from one place to another.",
    )

    with pytest.raises(ValueError, match="repetidas"):
        McqDefinition(SENTENCE, WORD, DEFINITION, options)


def test_correct_definition_must_be_among_the_options() -> None:
    options = (*DISTRACTORS, "eat something sweet")

    with pytest.raises(ValueError, match="no está entre las opciones"):
        McqDefinition(SENTENCE, WORD, DEFINITION, options)


def test_an_option_without_words_is_rejected() -> None:
    options = (DEFINITION, DISTRACTORS[0], DISTRACTORS[1], " ... ")

    with pytest.raises(ValueError, match="sin ninguna palabra"):
        McqDefinition(SENTENCE, WORD, DEFINITION, options)


def test_correct_definition_matches_by_words_not_by_spelling() -> None:
    """La definición guardada y su opción pueden diferir en mayúsculas y
    puntuación: siguen siendo la misma."""
    options = ("Spend a certain length of time; reside temporarily.", *DISTRACTORS)

    exercise = McqDefinition(SENTENCE, WORD, DEFINITION, options)

    assert exercise.answer_index == 0


# Estilo al mostrar.


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        # Una glosa de WordNet: minúscula y sin punto.
        ("reside temporarily", "Reside temporarily."),
        # Una del modelo: ya viene con mayúscula y punto.
        ("Reside temporarily.", "Reside temporarily."),
        # Espacios sobrantes, dentro y en los extremos.
        ("  reside   temporarily ", "Reside temporarily."),
        # Otros signos que ya cierran la frase.
        ("why would anyone stay?", "Why would anyone stay?"),
        ("and so on…", "And so on…"),
        # Un paréntesis final no cierra la frase.
        ("a temporary stay (e.g., as a guest)", "A temporary stay (e.g., as a guest)."),
        # La primera letra, aunque vaya dentro del paréntesis inicial.
        ("(law) a party to a lawsuit", "(Law) a party to a lawsuit."),
        # Siglas: el resto del texto no se toca.
        ("a citizen of the U.S.", "A citizen of the U.S."),
        ("DNA found in every cell", "DNA found in every cell."),
    ],
)
def test_options_are_displayed_with_the_same_style(text: str, shown: str) -> None:
    assert displayed(text) == shown


def test_display_keeps_the_original_text() -> None:
    exercise = _exercise(7)

    assert exercise.displayed_options == tuple(
        displayed(option) for option in exercise.options
    )
    assert DEFINITION in exercise.options
    assert all(option.endswith(".") for option in exercise.displayed_options)
