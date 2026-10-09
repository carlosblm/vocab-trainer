"""Prueba la política de D-025 sobre hechos escritos a mano, sin léxico.

Un caso por estado y, después, el orden entre ellos: cada par de
comprobaciones consecutivas con unos hechos que cumplen las dos, para ver cuál
gana.
"""

import pytest

from vocab.domain.definition_policy import (
    DefinitionDecision,
    DefinitionStatus,
    LexiconFacts,
    Sense,
    decide_definition,
)

ONE_SENSE = (Sense("crave-1", "have an urgent desire for"),)
TWO_SENSES = (
    Sense("come-1", "move toward"),
    Sense("come-2", "reach a destination"),
)


def _facts(
    *,
    pos_supported: bool = True,
    term_lemmas: frozenset[str] = frozenset({"crave"}),
    senses: tuple[Sense, ...] = ONE_SENSE,
) -> LexiconFacts:
    return LexiconFacts(
        pos_supported=pos_supported, term_lemmas=term_lemmas, senses=senses
    )


# Un caso por estado.


def test_unsupported_category_is_pos_unmapped() -> None:
    facts = LexiconFacts(pos_supported=False, term_lemmas=frozenset(), senses=())

    decision = decide_definition("bevel", None, facts)

    assert decision == DefinitionDecision(DefinitionStatus.POS_UNMAPPED)


def test_form_without_lemmas_is_form_not_found() -> None:
    decision = decide_definition("gumshoe", None, _facts(term_lemmas=frozenset()))

    assert decision.status is DefinitionStatus.FORM_NOT_FOUND


@pytest.mark.parametrize(
    "term_lemmas",
    [frozenset({"wan", "wane"}), frozenset({"wane"})],
    ids=["lemma_with_others", "lemma_missing"],
)
def test_lexicon_lemmas_other_than_the_entry_lemma_disagree(
    term_lemmas: frozenset[str],
) -> None:
    """El caso de D-015: spaCy da `wan` para `waned`. Acompañado o ausente, el
    léxico no confirma el lema."""
    decision = decide_definition("wan", None, _facts(term_lemmas=term_lemmas))

    assert decision.status is DefinitionStatus.LEMMA_DISAGREES


def test_particle_is_lexical_unit() -> None:
    """`come up`: el significado está en la unidad, no en `come` (D-008)."""
    facts = _facts(term_lemmas=frozenset({"come"}), senses=TWO_SENSES)

    decision = decide_definition("come", "up", facts)

    assert decision == DefinitionDecision(DefinitionStatus.LEXICAL_UNIT)


def test_single_sense_is_eligible_with_its_gloss_and_id() -> None:
    decision = decide_definition("crave", None, _facts())

    assert decision == DefinitionDecision(
        DefinitionStatus.ELIGIBLE,
        definition="have an urgent desire for",
        sense_id="crave-1",
    )


def test_several_senses_are_polysemous() -> None:
    facts = _facts(term_lemmas=frozenset({"come"}), senses=TWO_SENSES)

    decision = decide_definition("come", None, facts)

    assert decision == DefinitionDecision(DefinitionStatus.POLYSEMOUS)


# El orden: cada comprobación gana a la siguiente.


def test_category_is_checked_before_the_form() -> None:
    facts = LexiconFacts(pos_supported=False, term_lemmas=frozenset(), senses=())

    assert decide_definition("x", None, facts).status is DefinitionStatus.POS_UNMAPPED


def test_form_is_checked_before_the_lemma() -> None:
    """Sin lemas, tampoco son `{lemma}`: gana la forma no encontrada."""
    facts = _facts(term_lemmas=frozenset(), senses=())

    decision = decide_definition("crave", None, facts)

    assert decision.status is DefinitionStatus.FORM_NOT_FOUND


def test_lemma_is_checked_before_the_lexical_unit() -> None:
    """Con partícula, pero con el lema en desacuerdo, gana el lema: lo que no
    se confirma es la palabra misma."""
    facts = _facts(term_lemmas=frozenset({"wan", "wane"}))

    decision = decide_definition("wan", "out", facts)

    assert decision.status is DefinitionStatus.LEMMA_DISAGREES


def test_lexical_unit_is_checked_before_counting_senses() -> None:
    """El caso de `chew up`: con partícula no basta un único sentido, porque
    el de la unidad puede ser falso en la frase."""
    facts = _facts(term_lemmas=frozenset({"chew"}), senses=ONE_SENSE)

    decision = decide_definition("chew", "up", facts)

    assert decision.status is DefinitionStatus.LEXICAL_UNIT


# Detalles.


def test_lemma_comparison_ignores_case() -> None:
    decision = decide_definition("Crave", None, _facts())

    assert decision.status is DefinitionStatus.ELIGIBLE


def test_confirmed_lemma_without_senses_is_an_error() -> None:
    """Sin partícula, un lema que el léxico confirma tiene sentidos. Si no los
    trae, el adaptador falló, y no hay estado que lo describa."""
    with pytest.raises(ValueError, match="incoherentes"):
        decide_definition("crave", None, _facts(senses=()))


@pytest.mark.parametrize(
    ("status", "definition", "sense_id"),
    [
        (DefinitionStatus.ELIGIBLE, None, None),
        (DefinitionStatus.ELIGIBLE, "a gloss", None),
        (DefinitionStatus.POLYSEMOUS, "a gloss", "come-1"),
    ],
)
def test_definition_travels_only_with_eligible(
    status: DefinitionStatus, definition: str | None, sense_id: str | None
) -> None:
    with pytest.raises(ValueError, match="ELIGIBLE"):
        DefinitionDecision(status, definition=definition, sense_id=sense_id)
