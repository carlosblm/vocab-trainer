"""Prueba la plantilla de degradación de `mcq_definition` (§7.3): qué candidatos
valen y que los tres elegidos pasan los validadores. Sin base de datos."""

import random
from datetime import UTC, datetime

import pytest

from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.distractor_validation import validate_distractors
from vocab.domain.exercises.definition_template import (
    DefinitionCandidate,
    choose_template_distractors,
)
from vocab.domain.models import Context, Entry

DEFINITION = "spend a certain length of time; reside temporarily"


def _context(definition: DefinitionDecision | None) -> Context:
    return Context(
        external_id="target",
        term="sojourned",
        raw_sentence="They sojourned there.",
        clean_sentence="They sojourned there.",
        is_truncated=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        pos="VERB",
        morph="Tense=Past|VerbForm=Fin",
        definition=definition,
    )


ELIGIBLE = DefinitionDecision(
    DefinitionStatus.ELIGIBLE,
    "oewn:2025",
    definition=DEFINITION,
    sense_id="sojourn-v-1",
)
CONTEXT = _context(ELIGIBLE)
ENTRY = Entry(term="sojourned", lemma="sojourn", lang="en", contexts=[CONTEXT])


def _candidate(
    sense_id: str,
    definition: str,
    *,
    lemma: str | None = None,
    pos: str = "VERB",
    lang: str = "en",
) -> DefinitionCandidate:
    return DefinitionCandidate(
        lemma=lemma or sense_id.split("-")[0],
        lang=lang,
        pos=pos,
        sense_id=sense_id,
        definition=definition,
    )


VALID = [
    _candidate("crave-v-1", "have an urgent desire for"),
    _candidate("gulp-v-1", "swallow hurriedly or greedily"),
    _candidate("lever-v-1", "move or force with a lever"),
    _candidate("perk-v-1", "gain or regain energy"),
]


def test_three_valid_candidates_make_a_template() -> None:
    distractors = choose_template_distractors(ENTRY, CONTEXT, VALID, random.Random(1))

    assert distractors is not None
    assert len(set(distractors)) == 3
    assert set(distractors) <= {candidate.definition for candidate in VALID}
    assert validate_distractors(DEFINITION, distractors, "en") == ()


def test_same_seed_gives_the_same_template() -> None:
    first = choose_template_distractors(ENTRY, CONTEXT, VALID, random.Random(3))
    second = choose_template_distractors(ENTRY, CONTEXT, VALID, random.Random(3))

    assert first == second


def test_fewer_than_three_candidates_give_none() -> None:
    assert (
        choose_template_distractors(ENTRY, CONTEXT, VALID[:2], random.Random(1)) is None
    )


@pytest.mark.parametrize(
    "excluded",
    [
        # Mismo lema: sería otra definición correcta de la palabra.
        _candidate("sojourn-v-2", "stay somewhere as a visitor", lemma="sojourn"),
        # Mismo sentido que la correcta, aunque venga de otro lema.
        _candidate("sojourn-v-1", "pay a short visit", lemma="visit"),
        # Otra categoría: la gramática de la definición la delataría.
        _candidate("stay-n-1", "continuing or remaining in a place", pos="NOUN"),
        # Otro idioma (§3.3.1).
        _candidate("quedar-v-1", "permanecer en un lugar", lang="es"),
    ],
    ids=["same_lemma", "same_sense", "other_pos", "other_lang"],
)
def test_candidate_that_does_not_fit_is_excluded(excluded: DefinitionCandidate) -> None:
    """Con dos válidos y el excluido no llegan a tres."""
    candidates = [VALID[0], VALID[1], excluded]

    assert (
        choose_template_distractors(ENTRY, CONTEXT, candidates, random.Random(1))
        is None
    )


def test_a_repeated_sense_counts_once() -> None:
    """El mismo sentido en dos contextos es un solo candidato."""
    candidates = [VALID[0], VALID[1], VALID[1]]

    assert (
        choose_template_distractors(ENTRY, CONTEXT, candidates, random.Random(1))
        is None
    )


@pytest.mark.parametrize(
    "rejected",
    [
        # D7: niega, y la correcta no.
        _candidate("idle-v-1", "not do anything useful"),
        # D1: es la correcta, con otra mayúscula y puntuación (sinónimo del
        # mismo synset).
        _candidate("stay-v-3", "Spend a certain length of time; reside temporarily."),
        # Básico: las mismas palabras que otro candidato, otro sentido.
        _candidate("hanker-v-1", "Have an urgent desire for."),
    ],
    ids=["negation", "overlaps_correct", "duplicate"],
)
def test_candidate_rejected_by_the_validators_is_skipped(
    rejected: DefinitionCandidate,
) -> None:
    """Con el rechazado no llegan a tres válidos, en cualquier orden."""
    candidates = [VALID[0], VALID[1], rejected]

    for seed in range(10):
        result = choose_template_distractors(
            ENTRY, CONTEXT, candidates, random.Random(seed)
        )
        assert result is None


def test_rejected_candidate_is_replaced_by_the_next_valid_one() -> None:
    candidates = [_candidate("idle-v-1", "not do anything useful"), *VALID[:3]]

    for seed in range(10):
        result = choose_template_distractors(
            ENTRY, CONTEXT, candidates, random.Random(seed)
        )
        assert result is not None
        assert "not do anything useful" not in result


@pytest.mark.parametrize(
    "decision",
    [None, DefinitionDecision(DefinitionStatus.POLYSEMOUS, "oewn:2025")],
    ids=["not_evaluated", "polysemous"],
)
def test_only_eligible_contexts_have_a_template(
    decision: DefinitionDecision | None,
) -> None:
    with pytest.raises(ValueError, match="eligible"):
        choose_template_distractors(ENTRY, _context(decision), VALID, random.Random(1))
