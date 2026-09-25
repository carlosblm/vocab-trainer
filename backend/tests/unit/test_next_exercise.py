"""Prueba el caso de uso `next_exercise` con un repositorio falso y un azar
controlado: sin base de datos y con resultado determinista.

Este módulo no importa nada de `vocab.adapters`.
"""

import logging
import random
from datetime import UTC, datetime

from vocab.application.next_exercise import ChoiceFallback, next_exercise
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.domain.models import Context, Entry

PAST = "Tense=Past|VerbForm=Fin"


class FakeRepository:
    """Devuelve las entradas que recibe y anota qué se le pidió.

    `candidates` son las entradas de las que salen los distractores; por
    defecto ninguna.
    """

    def __init__(
        self, entries: list[Entry], candidates: list[Entry] | None = None
    ) -> None:
        self._entries = entries
        self._candidates = candidates or []
        self.requested_user_ids: list[int] = []
        self.candidate_reads = 0

    def ensure_user(self) -> int:
        return 7

    def list_learning_entries_with_usable_context(self, user_id: int) -> list[Entry]:
        self.requested_user_ids.append(user_id)
        return self._entries

    def list_non_noise_entries(self, user_id: int) -> list[Entry]:
        self.candidate_reads += 1
        return self._candidates


class InOrder(random.Random):
    """Azar trucado: toda permutación deja la población en su orden."""

    def sample(self, population, k, *, counts=None):
        return list(population)[:k]

    def shuffle(self, x):
        pass


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
    pos: str | None = None,
    morph: str | None = None,
) -> Context:
    return Context(
        external_id=external_id,
        term=term,
        raw_sentence=raw if raw is not None else sentence,
        clean_sentence=sentence,
        is_truncated=truncated,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        pos=pos,
        morph=morph,
    )


def _entry(lemma: str, contexts: list[Context], term: str | None = None) -> Entry:
    return Entry(
        term=term or contexts[0].term, lemma=lemma, lang="en", contexts=contexts
    )


def _past(lemma: str, term: str) -> Entry:
    return _entry(
        lemma, [_context(f"c-{term}", term, f"They {term} it.", pos="VERB", morph=PAST)]
    )


def _writing(repository: FakeRepository, rng: random.Random) -> ClozeOriginal | None:
    """La variante de escritura, que es la que usan los tests de selección."""
    item = next_exercise(repository, rng, choice=False)
    if item is None:
        return None
    assert isinstance(item.exercise, ClozeOriginal)
    assert item.fallback is None
    return item.exercise


# --- Selección de entrada y contexto


def test_nothing_to_study_gives_none():
    assert next_exercise(FakeRepository([]), random.Random(0), choice=True) is None


def test_entries_are_requested_for_the_single_user():
    repository = FakeRepository([])

    next_exercise(repository, random.Random(0), choice=False)

    assert repository.requested_user_ids == [7]


def test_word_and_clean_sentence_come_from_the_context_not_the_entry():
    """La entrada guarda `relied`; este contexto se consultó como `rely`
    (D-020). La frase es la limpia, que es la que se muestra tras un fallo."""
    context = _context("l2", "rely", "I rely on you.", raw=" I rely on you.[59] ")
    repository = FakeRepository([_entry("rely", [context], term="relied")])

    exercise = _writing(repository, random.Random(0))

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

    first = _writing(repository, InOrder())
    last = _writing(repository, Reversed())

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

    exercise = _writing(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."


def test_same_seed_gives_the_same_exercise():
    entries = [
        _entry(f"word{i}", [_context(f"l{i}", f"word{i}", f"A word{i} here.")])
        for i in range(50)
    ]
    repository = FakeRepository(entries)

    first = _writing(repository, random.Random(42))
    second = _writing(repository, random.Random(42))

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
        exercise = _writing(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."
    assert "broken" in caplog.text


def test_entry_whose_contexts_all_fail_gives_way_to_another():
    entries = [
        _entry("rely", [_context("broken", "rely", "Nothing to see here.")]),
        _entry("tide", [_context("good", "tide", "The tide rose.")]),
    ]

    exercise = _writing(FakeRepository(entries), InOrder())

    assert exercise is not None and exercise.sentence == "The tide rose."


def test_no_context_admitting_an_exercise_gives_none(caplog):
    entries = [_entry("rely", [_context("broken", "rely", "Nothing to see here.")])]

    with caplog.at_level(logging.WARNING):
        exercise = _writing(FakeRepository(entries), random.Random(0))

    assert exercise is None
    assert "broken" in caplog.text


# --- Variante de elección (D-022)

TARGET = _entry(
    "rely",
    [_context("r1", "relied", "She relied on luck.", pos="VERB", morph=PAST)],
)


def test_choice_gives_the_cloze_of_the_chosen_context_and_four_options():
    """La entrada elegida también llega entre los candidatos, como en la base:
    la regla la descarta por lema."""
    candidates = [TARGET, _past("toss", "tossed"), _past("ease", "eased")]
    candidates.append(_past("wane", "waned"))
    repository = FakeRepository([TARGET], candidates)

    item = next_exercise(repository, InOrder(), choice=True)

    assert item is not None and item.fallback is None
    assert isinstance(item.exercise, ClozeOriginalChoice)
    assert item.exercise.cloze == ClozeOriginal("She relied on luck.", "relied")
    assert item.exercise.options == ("relied", "tossed", "eased", "waned")


def test_choice_without_enough_distractors_falls_back_to_writing_and_says_why():
    repository = FakeRepository([TARGET], [TARGET, _past("toss", "tossed")])

    item = next_exercise(repository, InOrder(), choice=True)

    assert item is not None
    assert item.exercise == ClozeOriginal("She relied on luck.", "relied")
    assert item.fallback == ChoiceFallback(
        pos="VERB", morph=PAST, available=1, needed=3
    )


def test_fallback_of_an_unanalyzed_answer_says_there_is_no_form_to_match():
    entry = _entry("rely", [_context("r1", "relied", "She relied on luck.")])
    candidates = [_past(lemma, f"{lemma}ed") for lemma in ("toss", "ease", "wane")]

    item = next_exercise(FakeRepository([entry], candidates), InOrder(), choice=True)

    assert item is not None
    assert item.fallback == ChoiceFallback(pos=None, morph=None, available=0, needed=3)


def test_candidates_are_read_only_for_the_choice_variant():
    repository = FakeRepository([TARGET])

    next_exercise(repository, random.Random(0), choice=False)
    assert repository.candidate_reads == 0

    next_exercise(repository, random.Random(0), choice=True)
    assert repository.candidate_reads == 1


def test_same_seed_gives_the_same_options():
    candidates = [
        _past(lemma, f"{lemma}ed") for lemma in ("toss", "ease", "wane", "jump", "kick")
    ]
    repository = FakeRepository([TARGET], candidates)

    first = next_exercise(repository, random.Random(42), choice=True)
    second = next_exercise(repository, random.Random(42), choice=True)

    assert first == second
