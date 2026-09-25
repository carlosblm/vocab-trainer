"""El tipo de la variante de elección (D-022): un `ClozeOriginal` y cuatro
opciones fijadas al crearlo."""

import pytest

from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice

CLOZE = ClozeOriginal(
    sentence="Biases in context The claim to identify biases.", word="Biases"
)


def test_options_are_kept_in_the_order_they_were_fixed():
    exercise = ClozeOriginalChoice(
        cloze=CLOZE, options=("Tides", "Biases", "Crops", "Nests")
    )

    assert exercise.options == ("Tides", "Biases", "Crops", "Nests")
    assert exercise.cloze.masked_sentence.startswith("_____ in context")


def test_correction_is_the_writing_variant_one():
    """En minúscula, como `ClozeOriginal`: da igual cómo se muestre la
    opción."""
    exercise = ClozeOriginalChoice(
        cloze=CLOZE, options=("tides", "biases", "crops", "nests")
    )

    assert exercise.is_correct("biases")
    assert not exercise.is_correct("tides")


@pytest.mark.parametrize(
    "options",
    [
        ("Biases", "Tides", "Crops"),
        ("Biases", "Tides", "Crops", "Nests", "Moats"),
        ("Biases", "Tides", "tides", "Crops"),
        ("Tides", "Crops", "Nests", "Moats"),
    ],
    ids=["three", "five", "repeated", "answer-missing"],
)
def test_invalid_options_are_rejected(options):
    with pytest.raises(ValueError):
        ClozeOriginalChoice(cloze=CLOZE, options=options)
