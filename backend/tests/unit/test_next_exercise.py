"""Prueba el caso de uso `next_exercise` con un repositorio falso y un azar
controlado: sin base de datos y con resultado determinista.

Este módulo no importa nada de `vocab.adapters`.
"""

import logging
import random
from datetime import UTC, datetime

from vocab.application.next_exercise import next_exercise
from vocab.domain.models import Context, Entry


class FakeRepository:
    """Devuelve las entradas que recibe y anota para qué usuario se pidieron.

    `candidates` son las entradas de las que salen los distractores; por
    defecto ninguna.
    """

    def __init__(
        self, entries: list[Entry], candidates: list[Entry] | None = None
    ) -> None:
        self._entries = entries
        self._candidates = candidates or []
        self.requested_user_ids: list[int] = []

    def ensure_user(self) -> int:
        return 7

    def list_learning_entries_with_usable_context(self, user_id: int) -> list[Entry]:
        self.requested_user_ids.append(user_id)
        return self._entries

    def list_non_noise_entries(self, user_id: int) -> list[Entry]:
        return self._candidates


class InOrder(random.Random):
    """Azar trucado: toda permutación deja la población en su orden."""

    def sample(self, population, k, *, counts=None):
        return list(population)[:k]


class Reversed(random.Random):
    """Azar trucado: toda permutación invierte la población."""

    def sample(self, population, k, *, counts=None):
        return list(reversed(population))[:k]


def _context(
    external_id: str,
    term: str,
    sentence: str,
    *,
    raw: str | None = None,
    truncated: bool = False,
) -> Context:
    return Context(
        external_id=external_id,
        term=term,
        raw_sentence=raw if raw is not None else sentence,
        clean_sentence=sentence,
        is_truncated=truncated,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _entry(lemma: str, contexts: list[Context], term: str | None = None) -> Entry:
    return Entry(
        term=term or contexts[0].term, lemma=lemma, lang="en", contexts=contexts
    )


def test_nothing_to_study_gives_none():
    assert next_exercise(FakeRepository([]), random.Random(0)) is None


def test_entries_are_requested_for_the_single_user():
    repository = FakeRepository([])

    next_exercise(repository, random.Random(0))

    assert repository.requested_user_ids == [7]


def test_word_and_clean_sentence_come_from_the_context_not_the_entry():
    """La entrada guarda `relied`; este contexto se consultó como `rely`
    (D-020). La frase es la limpia, que es la que se muestra tras un fallo."""
    context = _context("l2", "rely", "I rely on you.", raw=" I rely on you.[59] ")
    repository = FakeRepository([_entry("rely", [context], term="relied")])

    exercise = next_exercise(repository, random.Random(0))

    assert exercise is not None
    assert exercise.word == "rely"
    assert exercise.sentence == "I rely on you."


def test_rng_chooses_the_entry_and_then_the_context():
    entries = [
        _entry(
            "tide",
            [
                _context("t1", "tide", "The tide rose."),
                _context("t2", "tides", "The tides fell."),
            ],
        ),
        _entry(
            "rely",
            [
                _context("r1", "relied", "She relied on luck."),
                _context("r2", "rely", "I rely on you."),
            ],
        ),
    ]
    repository = FakeRepository(entries)

    first = next_exercise(repository, InOrder())
    last = next_exercise(repository, Reversed())

    assert first is not None and first.sentence == "The tide rose."
    assert last is not None and last.sentence == "I rely on you."


def test_only_usable_contexts_are_candidates():
    """El truncado va primero y el azar en orden lo elegiría si contara."""
    entry = _entry(
        "rely",
        [
            _context("l1", "relied", "They relied on the", truncated=True),
            _context("l2", "rely", "I rely on you."),
        ],
    )

    exercise = next_exercise(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."


def test_same_seed_gives_the_same_exercise():
    entries = [
        _entry(f"word{i}", [_context(f"l{i}", f"word{i}", f"A word{i} here.")])
        for i in range(50)
    ]
    repository = FakeRepository(entries)

    first = next_exercise(repository, random.Random(42))
    second = next_exercise(repository, random.Random(42))

    assert first == second


def test_context_without_the_word_is_skipped_with_a_warning(caplog):
    entry = _entry(
        "rely",
        [
            _context("broken", "rely", "Nothing to see here."),
            _context("good", "rely", "I rely on you."),
        ],
    )

    with caplog.at_level(logging.WARNING):
        exercise = next_exercise(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."
    assert "broken" in caplog.text


def test_entry_whose_contexts_all_fail_gives_way_to_another():
    entries = [
        _entry("rely", [_context("broken", "rely", "Nothing to see here.")]),
        _entry("tide", [_context("good", "tide", "The tide rose.")]),
    ]

    exercise = next_exercise(FakeRepository(entries), InOrder())

    assert exercise is not None and exercise.sentence == "The tide rose."


def test_no_context_admitting_an_exercise_gives_none(caplog):
    entries = [_entry("rely", [_context("broken", "rely", "Nothing to see here.")])]

    with caplog.at_level(logging.WARNING):
        exercise = next_exercise(FakeRepository(entries), random.Random(0))

    assert exercise is None
    assert "broken" in caplog.text
