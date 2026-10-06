"""Validadores deterministas de distractores (§6.1: D1 y D7, más las
comprobaciones básicas), sobre el dominio puro.

Los distractores de §12.4 son reales: los generó el modelo en las pruebas
previas y motivaron D7 (D-005).
"""

import pytest

from vocab.domain.distractor_validation import (
    Violation,
    ViolationCode,
    validate_distractors,
)

RESILIENT = "able to recover quickly from hardship"


def test_section_12_4_negations_are_flagged_and_prone_to_is_a_known_limit():
    violations = validate_distractors(
        RESILIENT,
        (
            "Incapable of withstanding damage or adversity",
            "Prone to breaking down under pressure",
            "Lacking the ability to adapt to changing environments",
        ),
        "en",
    )

    # Límite conocido: «Prone to…» es un antónimo por significado, sin ningún
    # marcador de negación, y D7 no lo ve. Es terreno del juez (J2, F4).
    assert violations == (
        Violation(ViolationCode.NEGATION, 0),
        Violation(ViolationCode.NEGATION, 2),
    )


def test_definition_inside_a_distractor_only_as_characters_is_not_an_overlap():
    """`to rest` está en `to restore` como caracteres, no como tokens: la
    trampa de D-019."""
    violations = validate_distractors(
        "to rest",
        ("to restore order", "a pause for breath", "to stop working"),
        "en",
    )

    assert violations == ()


def test_definition_inside_distractor_distractor_inside_definition_and_equal():
    violations = validate_distractors(
        "have an urgent desire for",
        (
            "have an urgent desire for food",
            "an urgent desire",
            "Have an urgent desire for.",
        ),
        "en",
    )

    assert violations == (
        Violation(ViolationCode.OVERLAPS_CORRECT, 0),
        Violation(ViolationCode.OVERLAPS_CORRECT, 1),
        Violation(ViolationCode.OVERLAPS_CORRECT, 2),
    )


def test_negation_does_not_flag_when_the_correct_definition_also_negates():
    violations = validate_distractors(
        "having no known name",
        ("having no fixed address", "never given a title", "known by everyone"),
        "en",
    )

    assert violations == ()


def test_typographic_apostrophe_contraction_is_a_negation():
    violations = validate_distractors(
        RESILIENT,
        ("easily hurt by criticism", "doesn’t recover after a setback", "slow to heal"),
        "en",
    )

    assert violations == (Violation(ViolationCode.NEGATION, 1),)


def test_quotes_around_a_distractor_do_not_hide_negation_or_overlap():
    """Los apóstrofos de los bordes son comillas: «'Not» da `not`."""
    violations = validate_distractors(
        RESILIENT,
        (
            "'Not able to cope with change'",
            "'able to recover quickly from hardship'",
            "slow to heal",
        ),
        "en",
    )

    assert violations == (
        Violation(ViolationCode.OVERLAPS_CORRECT, 1),
        Violation(ViolationCode.NEGATION, 0),
    )


def test_distractors_differing_only_in_case_or_punctuation_are_duplicates():
    """Se marca el posterior: el primero sigue siendo válido."""
    violations = validate_distractors(
        RESILIENT,
        ("Easily broken.", "slow to heal", "EASILY, broken"),
        "en",
    )

    assert violations == (Violation(ViolationCode.DUPLICATE, 2),)


def test_punctuation_only_distractor_is_empty_and_not_an_overlap():
    """La secuencia vacía está contenida en todas: D1 no se aplica."""
    violations = validate_distractors(
        RESILIENT,
        ("easily hurt by criticism", "…?!", "slow to heal"),
        "en",
    )

    assert violations == (Violation(ViolationCode.EMPTY, 1),)


def test_all_violations_are_reported_in_check_order():
    """No se para en la primera: vacío, duplicado, D1 y D7, y dentro de cada
    comprobación por distractor."""
    violations = validate_distractors(
        RESILIENT,
        ("not able to cope", "", "Not able to cope!"),
        "en",
    )

    assert violations == (
        Violation(ViolationCode.EMPTY, 1),
        Violation(ViolationCode.DUPLICATE, 2),
        Violation(ViolationCode.NEGATION, 0),
        Violation(ViolationCode.NEGATION, 2),
    )


def test_correct_definition_without_tokens_is_rejected():
    with pytest.raises(ValueError):
        validate_distractors(
            "…", ("easily hurt", "slow to heal", "quick to anger"), "en"
        )


def test_language_without_negation_markers_is_rejected():
    """Sin lista, D7 daría por bueno cualquier distractor que niegue."""
    with pytest.raises(ValueError, match="'es'"):
        validate_distractors(
            RESILIENT, ("easily hurt", "slow to heal", "quick to anger"), "es"
        )


def test_accented_word_is_a_single_token():
    """Con `[a-z0-9']+`, `café` se partía en `caf`, y la definición correcta
    coincidía con el distractor: D1 lo marcaba."""
    violations = validate_distractors(
        "a small café",
        ("a small caf", "a large restaurant", "a busy street"),
        "en",
    )

    assert violations == ()


def test_decomposed_accent_is_the_same_token_as_the_composed_one():
    """La tilde como carácter aparte (NFD) no parte la palabra: tras NFC, el
    distractor es la definición correcta."""
    violations = validate_distractors(
        "a small café",
        ("a small café", "a large restaurant", "a busy street"),
        "en",
    )

    assert violations == (Violation(ViolationCode.OVERLAPS_CORRECT, 0),)
