"""Guarda de unidad léxica (D-008) con el modelo real de spaCy.

Frases inventadas: las del corpus son fragmentos de libros y no se versionan.
No necesita base de datos.
"""

from vocab.adapters.nlp.lexical_unit import detect_particles
from vocab.domain.cleaning import clean_sentence
from vocab.ports.normalizer import CleanedLookup


def _particle_of(word: str, sentence: str) -> str | None:
    lookup = CleanedLookup(
        external_id="test:1",
        word=word,
        lang="en",
        clean_sentence=clean_sentence(sentence),
    )
    return detect_particles([lookup])["test:1"]


def test_adjacent_particle_is_detected():
    """El caso de D-008, con la partícula pegada al verbo."""
    assert _particle_of("eased", "Electronics eased out the hydraulics.") == "out"


def test_separated_particle_is_detected():
    """Con el objeto en medio, la partícula ya no es la palabra siguiente, pero
    sigue colgando del verbo."""
    assert _particle_of("eased", "Electronics eased the hydraulics out.") == "out"


def test_preposition_is_not_detected():
    """`up` encabeza su propio complemento: es preposición, no partícula. Mismo
    verbo y misma palabra siguiente que «ran up the bill», que sí se marca."""
    assert _particle_of("ran", "He ran up the hill.") is None


def test_repeated_word_uses_first_occurrence():
    """Se mira la primera aparición, la misma de la que salen `pos` y `morph`:
    aquí lleva preposición y la segunda partícula, así que no se marca."""
    sentence = "He ran up the hill and later ran up a huge bill."
    assert _particle_of("ran", sentence) is None
