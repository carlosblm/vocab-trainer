"""Las lecturas de `StudyRepository` sobre Postgres: las entradas `learning` con
algún contexto utilizable, y las que aportan distractores (todo salvo `noise`),
reconstruidas completas.

Escribe entidades del dominio con `upsert_entries` y las vuelve a leer, así que
también prueba que las funciones de traducción entre fila y entidad no pierden
nada por el camino.
"""

from datetime import UTC, datetime

from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import UserRow
from vocab.domain.models import Context, Entry, EntryStatus


def _context(
    external_id: str,
    term: str,
    sentence: str,
    *,
    truncated: bool = False,
    pos: str | None = "VERB",
    morph: str | None = "Tense=Past|VerbForm=Fin",
) -> Context:
    return Context(
        external_id=external_id,
        term=term,
        raw_sentence=f" {sentence} ",
        clean_sentence=sentence,
        is_truncated=truncated,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        pos=pos,
        morph=morph,
        book_title="A Test Book",
        book_lang="en",
    )


def _entry(lemma: str, status: EntryStatus, contexts: list[Context]) -> Entry:
    return Entry(
        term=contexts[0].term,
        lemma=lemma,
        lang="en",
        external_id=f"en:{lemma}",
        status=status,
        contexts=contexts,
    )


def _store(
    repository: PostgresVocabularyRepository, user_id: int, entries: list[Entry]
) -> None:
    source_id = repository.register_source(
        user_id, "fake", "fake.db", f"checksum-{user_id}"
    )
    repository.upsert_entries(user_id, source_id, entries)


def test_learning_entry_comes_back_whole_with_every_context(session):
    """También el contexto truncado: elegir entre los utilizables es cosa de
    quien llama."""
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    entry = _entry(
        "rely",
        EntryStatus.LEARNING,
        [
            _context("l1", "relied", "She relied on luck."),
            _context("l2", "relied", "They relied on nothing but the", truncated=True),
            _context("l3", "rely", "I rely on you."),
        ],
    )
    _store(repository, user_id, [entry])

    assert repository.list_learning_entries_with_usable_context(user_id) == [entry]


def test_empty_features_and_missing_analysis_survive_as_different_values(session):
    """`""` es un token sin rasgos; `None`, uno no localizado (D-016). La base
    no puede convertir uno en otro."""
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    entry = _entry(
        "thus",
        EntryStatus.LEARNING,
        [
            _context("l1", "thus", "It was thus settled.", pos="ADV", morph=""),
            _context("l2", "thus", "And thus it ended.", pos=None, morph=None),
        ],
    )
    _store(repository, user_id, [entry])

    [stored] = repository.list_learning_entries_with_usable_context(user_id)

    assert [(c.pos, c.morph) for c in stored.contexts] == [("ADV", ""), (None, None)]


def test_known_and_noise_entries_are_left_out(session):
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    _store(
        repository,
        user_id,
        [
            _entry("rely", EntryStatus.LEARNING, [_context("l1", "rely", "I rely.")]),
            _entry("tide", EntryStatus.KNOWN, [_context("l2", "tide", "The tide.")]),
            _entry("the", EntryStatus.NOISE, [_context("l3", "the", "The end.")]),
        ],
    )

    entries = repository.list_learning_entries_with_usable_context(user_id)

    assert [entry.lemma for entry in entries] == ["rely"]


def test_learning_entry_without_usable_context_is_left_out(session):
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    _store(
        repository,
        user_id,
        [
            _entry(
                "rely",
                EntryStatus.LEARNING,
                [_context("l1", "relied", "They relied on the", truncated=True)],
            )
        ],
    )

    assert repository.list_learning_entries_with_usable_context(user_id) == []


def test_entries_of_another_user_are_left_out(session):
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    other = UserRow()
    session.add(other)
    session.flush()
    _store(
        repository,
        other.id,
        [_entry("rely", EntryStatus.LEARNING, [_context("l1", "rely", "I rely.")])],
    )

    assert repository.list_learning_entries_with_usable_context(user_id) == []
    assert repository.list_non_noise_entries(user_id) == []


def test_candidate_entries_are_learning_and_known_but_never_noise(session):
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    learning = _entry("rely", EntryStatus.LEARNING, [_context("l1", "rely", "I rely.")])
    known = _entry("tide", EntryStatus.KNOWN, [_context("l2", "tide", "The tide.")])
    noise = _entry("the", EntryStatus.NOISE, [_context("l3", "the", "The end.")])
    _store(repository, user_id, [learning, known, noise])

    assert repository.list_non_noise_entries(user_id) == [learning, known]


def test_candidate_entries_keep_unusable_and_unanalyzed_contexts(session):
    """A diferencia de la lectura de estudio, aquí no se descarta nada: qué
    contexto sirve como distractor lo decide la regla del dominio."""
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    entry = _entry(
        "rely",
        EntryStatus.LEARNING,
        [
            _context("l1", "relied", "They relied on the", truncated=True),
            _context("l2", "rely", "I rely on you.", pos=None, morph=None),
        ],
    )
    _store(repository, user_id, [entry])

    assert repository.list_non_noise_entries(user_id) == [entry]
