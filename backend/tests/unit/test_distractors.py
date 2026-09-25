"""La regla de distractores de la variante de elección (D-022), sobre el
dominio puro: sin base de datos, sin spaCy y con el azar controlado."""

import random
from datetime import UTC, datetime

import pytest

from vocab.domain.exercises.distractors import choose_options
from vocab.domain.models import Context, Entry, EntryStatus

PAST = "Tense=Past|VerbForm=Fin"
GERUND = "Aspect=Prog|Tense=Pres|VerbForm=Part"


class InOrder(random.Random):
    """Azar trucado: `sample` toma los primeros y `shuffle` no mueve nada."""

    def sample(self, population, k, *, counts=None):
        return list(population)[:k]

    def shuffle(self, x):
        pass


def _context(term: str, pos: str | None = "VERB", morph: str | None = PAST) -> Context:
    return Context(
        external_id=f"ctx-{term}",
        term=term,
        raw_sentence=f"They {term} it.",
        clean_sentence=f"They {term} it.",
        is_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        pos=pos,
        morph=morph,
    )


def _entry(
    lemma: str,
    contexts: list[Context],
    status: EntryStatus = EntryStatus.LEARNING,
    lang: str = "en",
) -> Entry:
    return Entry(
        term=contexts[0].term, lemma=lemma, lang=lang, status=status, contexts=contexts
    )


ANSWER = _context("relied")
TARGET = _entry("rely", [ANSWER])


def _past(
    lemma: str,
    term: str,
    status: EntryStatus = EntryStatus.LEARNING,
    lang: str = "en",
) -> Entry:
    return _entry(lemma, [_context(term)], status=status, lang=lang)


def test_distractors_share_category_and_features_with_the_answer():
    """El gerundio, el sustantivo y un AUX con los mismos rasgos no encajan en
    el hueco de un verbo en pasado."""
    candidates = [
        _entry("crave", [_context("craving", morph=GERUND)]),
        _entry("stake", [_context("stake", pos="NOUN", morph="Number=Sing")]),
        _entry("have", [_context("had", pos="AUX")]),
        _past("toss", "tossed"),
        _past("ease", "eased"),
        _past("wane", "waned"),
    ]

    options = choose_options(TARGET, ANSWER, candidates, InOrder())

    assert options == ("relied", "tossed", "eased", "waned")


def test_distractors_come_from_other_lemmas():
    """`learnt` comparte lema con `learned`: serían dos respuestas correctas."""
    answer = _context("learned")
    target = _entry("learn", [answer, _context("learnt")])
    candidates = [target, _past("toss", "tossed"), _past("ease", "eased")]

    assert choose_options(target, answer, candidates, InOrder()) is None

    options = choose_options(
        target, answer, [*candidates, _past("wane", "waned")], InOrder()
    )
    assert options is not None and "learnt" not in options


def test_noise_entries_never_supply_distractors():
    candidates = [
        _past("do", "did", status=EntryStatus.NOISE),
        _past("toss", "tossed"),
        _past("ease", "eased"),
    ]

    assert choose_options(TARGET, ANSWER, candidates, InOrder()) is None


def test_known_entries_do_supply_distractors():
    candidates = [
        _past("toss", "tossed", status=EntryStatus.KNOWN),
        _past("ease", "eased"),
        _past("wane", "waned"),
    ]

    assert choose_options(TARGET, ANSWER, candidates, InOrder()) is not None


def test_other_languages_never_supply_distractors():
    candidates = [
        _past("confiar", "confió", lang="es"),
        _past("toss", "tossed"),
        _past("ease", "eased"),
    ]

    assert choose_options(TARGET, ANSWER, candidates, InOrder()) is None


def test_repeated_forms_count_once():
    candidates = [
        _past("toss", "tossed"),
        _entry("tossing", [_context("Tossed")]),
        _past("ease", "eased"),
    ]

    assert choose_options(TARGET, ANSWER, candidates, InOrder()) is None


def test_a_form_identical_to_the_answer_is_never_a_distractor():
    """Otro lema con la misma escritura daría dos opciones correctas."""
    candidates = [
        _past("relied", "Relied"),
        _past("toss", "tossed"),
        _past("ease", "eased"),
    ]

    assert choose_options(TARGET, ANSWER, candidates, InOrder()) is None


def test_fewer_than_three_candidates_gives_none():
    """Sin tres distractores no se relaja la gramática ni se reducen las
    opciones: quien llama recurre a la variante de escritura."""
    two = [_past("toss", "tossed"), _past("ease", "eased")]

    assert choose_options(TARGET, ANSWER, two, InOrder()) is None
    assert choose_options(TARGET, ANSWER, [*two, _past("wane", "waned")], InOrder())


def test_unanalyzed_answer_gives_none():
    """Sin análisis no hay forma que igualar, ni siquiera con candidatos
    igual de vacíos."""
    answer = _context("relied", pos=None, morph=None)
    target = _entry("rely", [answer])
    candidates = [
        _entry(lemma, [_context(term, pos=None, morph=None)])
        for lemma, term in [("toss", "tossed"), ("ease", "eased"), ("wane", "waned")]
    ]

    assert choose_options(target, answer, candidates, InOrder()) is None


@pytest.mark.parametrize(
    ("answer_term", "expected"),
    [
        ("relied", ("relied", "tossed", "eased", "waned")),
        ("Relied", ("Relied", "Tossed", "Eased", "Waned")),
        ("RELIED", ("RELIED", "TOSSED", "EASED", "WANED")),
        ("ReLied", ("relied", "tossed", "eased", "waned")),
    ],
    ids=["lower", "capitalized", "upper", "mixed"],
)
def test_every_option_is_written_like_the_answer(answer_term, expected):
    """Los candidatos llegan con su propia escritura; si la conservaran, la
    mayúscula delataría la respuesta."""
    answer = _context(answer_term)
    target = _entry("rely", [answer])
    candidates = [
        _past("toss", "Tossed"),
        _past("ease", "EASED"),
        _past("wane", "waned"),
    ]

    assert choose_options(target, answer, candidates, InOrder()) == expected


def test_same_seed_gives_the_same_options_and_the_answer_is_always_one_of_them():
    candidates = [
        _past(lemma, f"{lemma}ed") for lemma in ("toss", "ease", "wane", "jump", "kick")
    ]

    first = choose_options(TARGET, ANSWER, candidates, random.Random(42))
    second = choose_options(TARGET, ANSWER, candidates, random.Random(42))

    assert first == second
    assert first is not None and len(first) == 4 and first.count("relied") == 1
