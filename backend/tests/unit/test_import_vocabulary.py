"""Prueba el caso de uso `import_vocabulary` con dobles de los tres puertos:
sin base de datos y sin spaCy.

Este módulo no importa nada de `vocab.adapters`. Si alguna vez hiciera falta,
sería señal de que un puerto está incompleto.
"""

from datetime import UTC, datetime

from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.models import Entry, EntryStatus
from vocab.ports.importer import RawLookup
from vocab.ports.normalizer import CleanedLookup, NormalizedWord, Normalizer
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


def _fake_normalizer(
    analysis_by_word: dict[str, tuple[str, str | None]],
    reverse: bool = False,
) -> Normalizer:
    """Normalizador falso: (lema, categoría) fijos por palabra, sin spaCy.

    `reverse` devuelve los resultados en orden inverso al de entrada. El
    puerto no promete orden, así que un doble que lo altera es legítimo.
    """

    def normalizer(cleaned_lookups: list[CleanedLookup]) -> list[NormalizedWord]:
        lemma_and_pos = (analysis_by_word[item.word] for item in cleaned_lookups)
        result = [
            NormalizedWord(external_id=item.external_id, lemma=lemma, pos=pos)
            for item, (lemma, pos) in zip(cleaned_lookups, lemma_and_pos, strict=True)
        ]
        return result[::-1] if reverse else result

    return normalizer


def test_two_forms_sharing_lemma_produce_one_entry_with_two_contexts():
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 2, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB"), "rely": ("rely", "VERB")}
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert len(repository.entries) == 1
    entry = repository.entries[0]
    assert entry.lemma == "rely"
    assert len(entry.contexts) == 2
    assert {c.external_id for c in entry.contexts} == {"l1", "l2"}


def test_each_context_keeps_its_own_looked_up_form():
    """El término de la entrada es el de la consulta más antigua; cada contexto
    conserva el suyo (D-020). Sin eso, `rely` no se localiza en «She relied on
    luck.»."""
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB"), "rely": ("rely", "VERB")}
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    entry = repository.entries[0]
    assert entry.term == "relied"
    assert {c.external_id: c.term for c in entry.contexts} == {
        "l1": "relied",
        "l2": "rely",
    }


def test_looked_up_word_reaches_the_domain_rule():
    """No prueba la regla —eso es `test_entry.py`— sino que el caso de uso le
    entrega la palabra consultada y su idioma."""
    lookups = [
        _lookup("the", "l1", "The bridge held.", datetime(2026, 1, 1, tzinfo=UTC))
    ]
    normalizer = _fake_normalizer({"the": ("the", "DET")})
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert repository.entries[0].status is EntryStatus.NOISE


def test_context_pos_belongs_to_its_own_lookup_not_the_first():
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB"), "rely": ("rely", "NOUN")}
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    pos_by_context = {c.external_id: c.pos for c in repository.entries[0].contexts}
    assert pos_by_context == {"l1": "VERB", "l2": "NOUN"}


def test_results_are_paired_by_key_not_by_position():
    """El puerto no garantiza orden: reemparejar por posición asignaría el
    `pos` de una consulta a la otra."""
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB"), "rely": ("rely", "NOUN")}, reverse=True
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    pos_by_context = {c.external_id: c.pos for c in repository.entries[0].contexts}
    assert pos_by_context == {"l1": "VERB", "l2": "NOUN"}


def test_unresolved_word_keeps_its_context_with_no_pos():
    lookups = [
        _lookup("thole", "l1", "He held the thole.", datetime(2026, 1, 1, tzinfo=UTC))
    ]
    normalizer = _fake_normalizer({"thole": ("thole", None)})
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    assert repository.entries[0].contexts[0].pos is None


def test_raw_and_clean_sentence_are_preserved():
    dirty = "It proved resilient.[59] "
    lookups = [_lookup("resilient", "l1", dirty, datetime(2026, 1, 1, tzinfo=UTC))]
    normalizer = _fake_normalizer({"resilient": ("resilient", "ADJ")})
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, "fake.db")

    context = repository.entries[0].contexts[0]
    assert context.raw_sentence == dirty
    assert context.clean_sentence == "It proved resilient."
