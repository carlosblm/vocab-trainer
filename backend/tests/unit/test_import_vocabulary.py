"""Prueba el caso de uso `import_vocabulary` con dobles de los cuatro puertos:
sin base de datos, sin spaCy y sin léxico.

Este módulo no importa nada de `vocab.adapters`. Si alguna vez hiciera falta,
sería señal de que un puerto está incompleto.
"""

from datetime import UTC, datetime

from tests.unit.doubles import NO_CATEGORY, FakeLexicon

from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.definition_policy import (
    DefinitionDecision,
    DefinitionStatus,
    LexiconFacts,
    Sense,
)
from vocab.domain.models import Entry, EntryStatus
from vocab.ports.importer import RawLookup
from vocab.ports.normalizer import CleanedLookup, NormalizedWord, Normalizer
from vocab.ports.repository import ImportStats

PAST = "Tense=Past|VerbForm=Fin"
PRESENT = "Tense=Pres|VerbForm=Fin"
SINGULAR = "Number=Sing"


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

    def register_source(
        self, user_id: int, kind: str, filename: str, checksum: str
    ) -> int:
        return 1

    def upsert_entries(
        self, user_id: int, source_id: int, entries: list[Entry]
    ) -> ImportStats:
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
    analysis_by_word: dict[str, tuple[str, str | None, str | None]],
    reverse: bool = False,
    particles: dict[str, str] | None = None,
) -> Normalizer:
    """Normalizador falso: (lema, categoría, rasgos) fijos por palabra, sin
    spaCy, y la partícula de R1 de las palabras que estén en `particles`.

    `reverse` devuelve los resultados en orden inverso al de entrada. El
    puerto no promete orden, así que un doble que lo altera es legítimo.
    """
    particle_by_word = particles or {}

    def normalizer(cleaned_lookups: list[CleanedLookup]) -> list[NormalizedWord]:
        analyses = (analysis_by_word[item.word] for item in cleaned_lookups)
        result = [
            NormalizedWord(
                external_id=item.external_id,
                lemma=lemma,
                pos=pos,
                morph=morph,
                particle=particle_by_word.get(item.word),
            )
            for item, (lemma, pos, morph) in zip(cleaned_lookups, analyses, strict=True)
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
        {"relied": ("rely", "VERB", PAST), "rely": ("rely", "VERB", PRESENT)}
    )
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

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
        {"relied": ("rely", "VERB", PAST), "rely": ("rely", "VERB", PRESENT)}
    )
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

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
    normalizer = _fake_normalizer({"the": ("the", "DET", "Definite=Def|PronType=Art")})
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

    assert repository.entries[0].status is EntryStatus.NOISE


def test_context_analysis_belongs_to_its_own_lookup_not_the_first():
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB", PAST), "rely": ("rely", "NOUN", SINGULAR)}
    )
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

    analysis_by_context = {
        c.external_id: (c.pos, c.morph) for c in repository.entries[0].contexts
    }
    assert analysis_by_context == {"l1": ("VERB", PAST), "l2": ("NOUN", SINGULAR)}


def test_results_are_paired_by_key_not_by_position():
    """El puerto no garantiza orden: reemparejar por posición asignaría el
    `pos` y los rasgos de una consulta a la otra."""
    lookups = [
        _lookup(
            "relied", "l1", "She relied on luck.", datetime(2026, 1, 1, tzinfo=UTC)
        ),
        _lookup("rely", "l2", "I rely on you.", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    normalizer = _fake_normalizer(
        {"relied": ("rely", "VERB", PAST), "rely": ("rely", "NOUN", SINGULAR)},
        reverse=True,
    )
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

    analysis_by_context = {
        c.external_id: (c.pos, c.morph) for c in repository.entries[0].contexts
    }
    assert analysis_by_context == {"l1": ("VERB", PAST), "l2": ("NOUN", SINGULAR)}


def test_unresolved_word_keeps_its_context_with_no_analysis():
    lookups = [
        _lookup("thole", "l1", "He held the thole.", datetime(2026, 1, 1, tzinfo=UTC))
    ]
    normalizer = _fake_normalizer({"thole": ("thole", None, None)})
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

    context = repository.entries[0].contexts[0]
    assert context.pos is None
    assert context.morph is None


def test_raw_and_clean_sentence_are_preserved():
    dirty = "It proved resilient.[59] "
    lookups = [_lookup("resilient", "l1", dirty, datetime(2026, 1, 1, tzinfo=UTC))]
    normalizer = _fake_normalizer({"resilient": ("resilient", "ADJ", "Degree=Pos")})
    repository = FakeRepository()

    import_vocabulary(
        FakeImporter(lookups),
        repository,
        normalizer,
        FakeLexicon(default=NO_CATEGORY),
        "fake.db",
    )

    context = repository.entries[0].contexts[0]
    assert context.raw_sentence == dirty
    assert context.clean_sentence == "It proved resilient."


# La definición de cada contexto (D-033).

LEXICON = "fake:1"
WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _lexicon_facts(
    term_lemmas: set[str], senses: tuple[Sense, ...] = ()
) -> LexiconFacts:
    return LexiconFacts(
        pos_supported=True,
        term_lemmas=frozenset(term_lemmas),
        senses=senses,
        lexicon=LEXICON,
    )


ONE_SENSE = (Sense("sojourn-1", "reside temporarily"),)
TWO_SENSES = (Sense("bank-1", "sloping land"), Sense("bank-2", "a financial firm"))


def _definitions(repository: FakeRepository) -> dict[str, DefinitionDecision | None]:
    return {
        context.external_id: context.definition
        for entry in repository.entries
        for context in entry.contexts
    }


def test_each_context_gets_the_decision_of_its_facts() -> None:
    """Un contexto por estado. El caso de uso no decide nada: le pasa al
    dominio el lema de la entrada, la partícula y los hechos de su contexto."""
    lookups = [
        _lookup("Bevel", "unmapped", "Bevel smiled.", WHEN),
        _lookup("gumshoes", "not_found", "Be good gumshoes.", WHEN),
        _lookup("waned", "disagrees", "The light waned.", WHEN),
        _lookup("chewed", "unit", "It got chewed up.", WHEN),
        _lookup("sojourned", "eligible", "They sojourned there.", WHEN),
        _lookup("banks", "polysemous", "Along the banks.", WHEN),
    ]
    normalizer = _fake_normalizer(
        {
            "Bevel": ("bevel", "PROPN", "Number=Sing"),
            "gumshoes": ("gumshoe", "NOUN", "Number=Plur"),
            "waned": ("wan", "VERB", PAST),
            "chewed": ("chew", "VERB", PAST),
            "sojourned": ("sojourn", "VERB", PAST),
            "banks": ("bank", "NOUN", "Number=Plur"),
        },
        particles={"chewed": "up"},
    )
    lexicon = FakeLexicon(
        {
            "Bevel": LexiconFacts(
                pos_supported=False, term_lemmas=frozenset(), senses=(), lexicon=LEXICON
            ),
            "gumshoes": _lexicon_facts(set()),
            "waned": _lexicon_facts({"wan", "wane"}),
            "chewed": _lexicon_facts({"chew"}, ONE_SENSE),
            "sojourned": _lexicon_facts({"sojourn"}, ONE_SENSE),
            "banks": _lexicon_facts({"bank"}, TWO_SENSES),
        }
    )
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, lexicon, "fake.db")

    definitions = _definitions(repository)
    statuses = {
        key: decision.status if decision else None
        for key, decision in definitions.items()
    }
    assert statuses == {
        "unmapped": DefinitionStatus.POS_UNMAPPED,
        "not_found": DefinitionStatus.FORM_NOT_FOUND,
        "disagrees": DefinitionStatus.LEMMA_DISAGREES,
        "unit": DefinitionStatus.LEXICAL_UNIT,
        "eligible": DefinitionStatus.ELIGIBLE,
        "polysemous": DefinitionStatus.POLYSEMOUS,
    }
    assert definitions["eligible"] == DefinitionDecision(
        DefinitionStatus.ELIGIBLE,
        LEXICON,
        definition="reside temporarily",
        sense_id="sojourn-1",
    )


def test_r1_particle_is_stored_and_makes_a_lexical_unit() -> None:
    """Con partícula, `lexical_unit` aunque el lema tenga un único sentido: el
    caso de `chew up` (D-032)."""
    lookups = [_lookup("chewed", "l1", "It got chewed up.", WHEN)]
    normalizer = _fake_normalizer(
        {"chewed": ("chew", "VERB", PAST)}, particles={"chewed": "up"}
    )
    lexicon = FakeLexicon({"chewed": _lexicon_facts({"chew"}, ONE_SENSE)})
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, lexicon, "fake.db")

    context = repository.entries[0].contexts[0]
    assert context.particle == "up"
    assert context.definition == DefinitionDecision(
        DefinitionStatus.LEXICAL_UNIT, LEXICON
    )


def test_context_without_category_is_not_evaluated() -> None:
    """Sin `pos`, el contexto no llega al léxico y queda sin decisión, que no es
    `pos_unmapped` (D-016). Los demás van en un único lote."""
    lookups = [
        _lookup("thole", "l1", "He held the thole.", WHEN),
        _lookup("sojourned", "l2", "They sojourned there.", WHEN),
    ]
    normalizer = _fake_normalizer(
        {"thole": ("thole", None, None), "sojourned": ("sojourn", "VERB", PAST)}
    )
    lexicon = FakeLexicon({"sojourned": _lexicon_facts({"sojourn"}, ONE_SENSE)})
    repository = FakeRepository()

    import_vocabulary(FakeImporter(lookups), repository, normalizer, lexicon, "fake.db")

    definitions = _definitions(repository)
    assert definitions["l1"] is None
    assert definitions["l2"] is not None
    assert [[query.external_id for query in batch] for batch in lexicon.batches] == [
        ["l2"]
    ]
