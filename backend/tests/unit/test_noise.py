import pytest

from vocab.domain.noise import LookedUpWord, is_noise


@pytest.mark.parametrize("word", ["the", "of", "and", "A", "M", "which"])
def test_filters_function_words(word):
    assert is_noise(LookedUpWord(text=word, lang="en"))


@pytest.mark.parametrize("word", ["even", "beneath", "neither", "shall", "will", "own"])
def test_keeps_words_a_learner_would_look_up(word):
    """Funcionales gramaticalmente, pero vocabulario real para un B2.
    `even` aparece en el corpus significando *par*."""
    assert not is_noise(LookedUpWord(text=word, lang="en"))
