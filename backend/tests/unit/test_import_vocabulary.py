"""Prueba el caso de uso `import_vocabulary` con dobles de los tres puertos:
sin base de datos y sin spaCy.
"""

from datetime import UTC, datetime

from vocab.adapters.nlp.normalizer import CleanedLookup, NormalizedWord
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.models import Entry, EntryStatus
from vocab.ports.importer import RawLookup
from vocab.ports.repository import ImportStats


class FakeImporter:
    kind = "fake"

    def __init__(self, lookups: list[RawLookup]) -> None:
        self._lookups = lookups

    def checksum(self) -> str:
        return "fake-checksum"

    def read(self):
        return iter(self._lookups)


class FakeRepository:
    """Guarda las entradas recibidas tal cual, sin persistirlas."""

    def __init__(self) -> None:
        self.entries: list[Entry] = []

    def ensure_user(self) -> int:
        return 1

    def register_source(self, user_id, kind, filename, checksum) -> int:
        return 1

    def upsert_entries(self, user_id, source_id, entries: list[Entry]) -> ImportStats:
        self.entries = entries
        return ImportStats(
            entries_created=len(entries),
            entries_existing=0,
            contexts_created=sum(len(entry.contexts) for entry in entries),
            contexts_existing=0,
        )


def _lookup(word: str, external_id: str, sentence: str, when: datetime) -> RawLookup:
    return RawLookup(
        external_id=external_id,
        word=word,
        lang="en",
        sentence=sentence,
        looked_up_at=when,
    )


def _fake_normalizer(lemmas: dict[str, NormalizedWord]):
    """Normalizador falso: lema y pos fijos por palabra, sin spaCy."""

    def normalizer(cleaned_lookups: list[CleanedLookup]):
        return [(item.lookup, lemmas[item.lookup.word]) for item in cleaned_lookups]

    return normalizer


def test_two_forms_sharing_lemma_produce_one_entry_with_two_contexts():
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 2, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {
            "relied": NormalizedWord(lemma="rely", pos="VERB", tag="VBD"),
            "rely": NormalizedWord(lemma="rely", pos="VERB", tag="VBP"),
        }
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert len(repository.entries) == 1
    entry = repository.entries[0]
    assert entry.lemma == "rely"
    assert len(entry.contexts) == 2
    assert {c.external_id for c in entry.contexts} == {"l1", "l2"}


def test_group_where_every_lookup_is_noise_gets_noise_status():
    lookups = [
        _lookup("the", "l1", "The bridge held.", datetime(2026, 1, 1, tzinfo=UTC))
    ]
    normalizer = _fake_normalizer(
        {"the": NormalizedWord(lemma="the", pos="DET", tag="DT")}
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert repository.entries[0].status is EntryStatus.NOISE


def test_group_with_one_real_lookup_among_noise_gets_learning_status():
    # Lema compartido a propósito: el normalizador es falso, así que puede
    # agrupar "the" y "resilient" bajo el mismo lema para aislar la regla de
    # agregación de _entry_status de la lematización real de spaCy.
    lookups = [
        _lookup("the", "l1", "The bridge held.", datetime(2026, 1, 1, tzinfo=UTC)),
        _lookup(
            "resilient", "l2", "It proved resilient.", datetime(2026, 1, 2, tzinfo=UTC)
        ),
    ]
    normalizer = _fake_normalizer(
        {
            "the": NormalizedWord(lemma="shared", pos="DET", tag="DT"),
            "resilient": NormalizedWord(lemma="shared", pos="ADJ", tag="JJ"),
        }
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert repository.entries[0].status is EntryStatus.LEARNING


def test_context_pos_belongs_to_its_own_lookup_not_the_first():
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {
            "relied": NormalizedWord(lemma="rely", pos="VERB", tag="VBD"),
            "rely": NormalizedWord(lemma="rely", pos="NOUN", tag="NN"),
        }
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    pos_by_context = {c.external_id: c.pos for c in repository.entries[0].contexts}
    assert pos_by_context == {"l1": "VERB", "l2": "NOUN"}


def test_raw_and_clean_sentence_are_preserved():
    dirty = "It proved resilient.[59] "
    lookups = [_lookup("resilient", "l1", dirty, datetime(2026, 1, 1, tzinfo=UTC))]
    normalizer = _fake_normalizer(
        {"resilient": NormalizedWord(lemma="resilient", pos="ADJ", tag="JJ")}
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    context = repository.entries[0].contexts[0]
    assert context.raw_sentence == dirty
    assert context.clean_sentence == "It proved resilient."
