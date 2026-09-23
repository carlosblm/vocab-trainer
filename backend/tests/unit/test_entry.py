"""La regla de ruido decide con qué estado nace una entrada (D-013, D-014).

Se prueba directamente sobre el dominio: no hace falta ni caso de uso ni
normalizador falso que force dos palabras al mismo lema.
"""

from vocab.domain.models import Entry, EntryStatus
from vocab.domain.noise import LookedUpWord


def test_entry_from_a_function_word_is_born_noise():
    entry = Entry.new(
        word=LookedUpWord(text="the", lang="en"),
        lemma="the",
        external_id="en:the",
        contexts=[],
    )

    assert entry.status is EntryStatus.NOISE
    assert entry.term == "the"
    assert entry.lang == "en"


def test_entry_from_real_vocabulary_is_born_learning():
    entry = Entry.new(
        word=LookedUpWord(text="resilient", lang="en"),
        lemma="resilient",
        external_id="en:resilient",
        contexts=[],
    )

    assert entry.status is EntryStatus.LEARNING


def test_plain_constructor_keeps_the_status_it_receives():
    """Reconstruir una entrada guardada no recalcula nada: el `known` que puso
    el usuario sobrevive a la reimportación (D-014)."""
    entry = Entry(term="the", lemma="the", lang="en", status=EntryStatus.KNOWN)

    assert entry.status is EntryStatus.KNOWN
