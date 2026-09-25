"""El ejercicio `cloze_original` (D-019), sobre el dominio puro.

Las frases marcadas como reales vienen del corpus de septiembre de 2026; son
los casos que motivaron cada decisión.
"""

import re

import pytest

from vocab.domain.exercises.cloze_original import BLANK, ClozeOriginal


def test_single_occurrence_is_masked():
    exercise = ClozeOriginal(sentence="It proved resilient.", word="resilient")

    assert exercise.masked_sentence == f"It proved {BLANK}."
    assert exercise.answer == "resilient"


def test_word_is_located_ignoring_case_and_answer_keeps_the_sentence_form():
    """`Hence` y `hence` caen en la misma entrada (§4.1 de la propuesta)."""
    exercise = ClozeOriginal(sentence="Hence, the delay.", word="hence")

    assert exercise.masked_sentence == f"{BLANK}, the delay."
    assert exercise.answer == "Hence"


def test_substring_inside_another_word_is_not_masked():
    """Real: la subcadena `straw` aparece antes dentro de `straws`."""
    exercise = ClozeOriginal(
        sentence="clutch at straws, and the anchor is a plausible straw.",
        word="straw",
    )

    assert exercise.masked_sentence == (
        f"clutch at straws, and the anchor is a plausible {BLANK}."
    )


def test_word_present_only_as_substring_is_rejected():
    with pytest.raises(ValueError):
        ClozeOriginal(sentence="They clutch at straws.", word="straw")


def test_every_occurrence_is_masked():
    """Tapar una sola dejaría la respuesta a la vista (27 de los 999
    contextos de study repiten la palabra)."""
    exercise = ClozeOriginal(
        sentence="The tide came in and the tide went out.", word="tide"
    )

    assert exercise.masked_sentence == (
        f"The {BLANK} came in and the {BLANK} went out."
    )
    assert not re.search(r"\btide\b", exercise.masked_sentence, re.IGNORECASE)


def test_repetitions_with_different_case_are_all_masked():
    """Real: 2 de los 999 contextos de study repiten la palabra con
    mayúsculas distintas."""
    exercise = ClozeOriginal(
        sentence=(
            "Biases in context The claim to identify biases in human behaviour "
            "presupposes knowledge of what unbiased behaviour looks like."
        ),
        word="Biases",
    )

    assert exercise.masked_sentence.startswith(
        f"{BLANK} in context The claim to identify {BLANK} in human"
    )
    assert "unbiased" in exercise.masked_sentence
    assert exercise.answer == "Biases"
    assert exercise.is_correct("biases")


@pytest.mark.parametrize(
    ("sentence", "word", "masked"),
    [
        (
            "Resilient materials absorb impact.",
            "resilient",
            "{} materials absorb impact.",
        ),
        ("It proved resilient.", "resilient", "It proved {}."),
        ("It was resilient, and cheap.", "resilient", "It was {}, and cheap."),
        ("He called it “resilient” twice.", "resilient", "He called it “{}” twice."),
        ("“Daniel’s” car.", "Daniel", "“{}’s” car."),
    ],
    ids=[
        "sentence-start",
        "before-period",
        "before-comma",
        "curly-quotes",
        "possessive",
    ],
)
def test_punctuation_around_the_word_is_kept(sentence, word, masked):
    exercise = ClozeOriginal(sentence=sentence, word=word)

    assert exercise.masked_sentence == masked.format(BLANK)


def test_hyphen_counts_as_a_word_boundary():
    """Real: el Kindle guardó `savvy`, no el compuesto."""
    exercise = ClozeOriginal(
        sentence="the larger regional players were more tech-savvy.", word="savvy"
    )

    assert exercise.masked_sentence == (
        f"the larger regional players were more tech-{BLANK}."
    )


def test_absent_word_is_rejected():
    with pytest.raises(ValueError):
        ClozeOriginal(sentence="It proved resilient.", word="flood")


@pytest.mark.parametrize("word", ["", "   "], ids=["empty", "whitespace"])
def test_blank_word_is_rejected(word):
    """El patrón vacío encajaría al final de la frase y aceptaría `""` como
    respuesta correcta."""
    with pytest.raises(ValueError):
        ClozeOriginal(sentence="It proved resilient.", word=word)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (" Straw \n", True),
        ("STRAW", True),
        ("straws", False),
        ("straw.", False),
        ("", False),
    ],
    ids=["surrounding-spaces", "upper-case", "other-word", "punctuation", "empty"],
)
def test_correction_compares_lowered_and_stripped_only(response, expected):
    exercise = ClozeOriginal(sentence="A plausible straw.", word="straw")

    assert exercise.is_correct(response) is expected


def test_lemma_is_not_the_expected_answer():
    exercise = ClozeOriginal(sentence="She relied on luck.", word="relied")

    assert not exercise.is_correct("rely")


def test_same_sentence_and_word_give_the_same_exercise():
    """Sin azar ni posición: el ejercicio queda definido por sus dos campos."""
    first = ClozeOriginal(sentence="The tide turned.", word="tide")
    second = ClozeOriginal(sentence="The tide turned.", word="tide")

    assert first == second
    assert first.masked_sentence == second.masked_sentence


def test_sentence_is_kept_intact():
    """Es lo que se muestra tras un fallo y lo que D5 comparará con el libro."""
    sentence = "The tide came in and the tide went out."
    exercise = ClozeOriginal(sentence=sentence, word="tide")

    _ = exercise.masked_sentence

    assert exercise.sentence == sentence


def test_regex_metacharacters_in_the_word_are_literal():
    """Defensivo: ninguna de las palabras de los 999 contextos de study tiene
    caracteres que no sean de palabra."""
    exercise = ClozeOriginal(sentence="The UKS. and the U.S. army", word="U.S.")

    assert exercise.masked_sentence == f"The UKS. and the {BLANK} army"
    with pytest.raises(ValueError):
        ClozeOriginal(sentence="The UKS. army", word="U.S.")
