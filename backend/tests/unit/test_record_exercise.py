"""Prueba `record_exercise`: qué registro sale de cada resultado de
`next_exercise`, sin base de datos. La ida y vuelta por Postgres está en los
tests de integración.

Este módulo no importa nada de `vocab.adapters`.
"""

from datetime import UTC, datetime

from vocab.application.generate_distractors import (
    AcceptedAttempt,
    MalformedAttempt,
    ProviderUnavailable,
    RejectedAttempt,
    RetriesExhausted,
    UnavailableAttempt,
)
from vocab.application.next_exercise import (
    ClozeExercise,
    DefinitionExercise,
    DefinitionFallback,
    ExerciseRejected,
    ModelDistractors,
    NoGenerator,
    TemplateDistractors,
)
from vocab.application.record_exercise import exercise_record, record_exercise
from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.distractor_validation import Violation, ViolationCode
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import Context, ContextKey, Entry
from vocab.ports.distractor_generator import GeneratedDistractors, GeneratorIdentity
from vocab.ports.exercise_record import (
    AttemptOutcome,
    AttemptRecord,
    DegradationCode,
    DistractorSource,
    ExerciseRecord,
)

SENTENCE = "They sojourned in the hills."
SOJOURN = "spend a certain length of time; reside temporarily"
CONTEXT = Context(
    external_id="s1",
    term="sojourned",
    raw_sentence=SENTENCE,
    clean_sentence=SENTENCE,
    is_truncated=False,
    captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    pos="VERB",
    morph="Tense=Past|VerbForm=Fin",
    definition=DefinitionDecision(
        DefinitionStatus.ELIGIBLE,
        "oewn:2025",
        definition=SOJOURN,
        sense_id="sojourn-v-1",
    ),
)
ENTRY = Entry(term="sojourned", lemma="sojourn", lang="en", contexts=[CONTEXT])
KEY = ContextKey(lemma="sojourn", lang="en", external_id="s1")
MCQ = McqDefinition(
    SENTENCE,
    "sojourned",
    SOJOURN,
    (SOJOURN, "speak quietly", "work hard", "travel quickly"),
)
CLOZE = ClozeOriginal(SENTENCE, "sojourned")
SCRIPTED = GeneratorIdentity("scripted", "test")
UNAVAILABLE = "Ollama en http://localhost:1/api/chat: no se pudo conectar"


class FakeExerciseRepository:
    """Guarda los registros que recibe, con el usuario."""

    def __init__(self) -> None:
        self.saved: list[tuple[int, ExerciseRecord]] = []

    def ensure_user(self) -> int:
        return 7

    def save_exercise(self, user_id: int, record: ExerciseRecord) -> int:
        self.saved.append((user_id, record))
        return len(self.saved)


def test_record_is_saved_for_the_single_user_and_returns_its_id() -> None:
    repository = FakeExerciseRepository()
    item = ClozeExercise(ENTRY, CONTEXT, CLOZE)

    exercise_id = record_exercise(repository, item)

    assert exercise_id == 1
    assert repository.saved == [(7, exercise_record(item))]


def test_model_distractors_keep_the_generator_and_every_attempt() -> None:
    """Los tres resultados del historial, con los códigos que se guardan."""
    rejected = ("not stay", "stay", "leave")
    violations = (
        Violation(ViolationCode.NEGATION, 0),
        Violation(ViolationCode.OVERLAPS_CORRECT, 1),
    )
    attempts = (
        RejectedAttempt(rejected, violations),
        MalformedAttempt("no es JSON"),
        AcceptedAttempt(),
    )
    item = DefinitionExercise(ENTRY, CONTEXT, MCQ, ModelDistractors(SCRIPTED, attempts))

    assert exercise_record(item) == ExerciseRecord(
        context=KEY,
        exercise=MCQ,
        source=DistractorSource.MODEL,
        generator=SCRIPTED,
        attempts=(
            AttemptRecord(
                AttemptOutcome.REJECTED, distractors=rejected, violations=violations
            ),
            AttemptRecord(AttemptOutcome.MALFORMED, reason="no es JSON"),
            AttemptRecord(AttemptOutcome.ACCEPTED),
        ),
    )


def test_degradation_keeps_the_generator_it_was_tried_with() -> None:
    item = DefinitionExercise(
        ENTRY,
        CONTEXT,
        MCQ,
        TemplateDistractors(
            ProviderUnavailable(UNAVAILABLE),
            (UnavailableAttempt(UNAVAILABLE),),
            SCRIPTED,
        ),
    )

    record = exercise_record(item)

    assert record.source is DistractorSource.TEMPLATE
    assert record.generator == SCRIPTED
    assert record.degradation is DegradationCode.PROVIDER_UNAVAILABLE
    assert record.degradation_reason == UNAVAILABLE
    assert record.attempts == (
        AttemptRecord(AttemptOutcome.UNAVAILABLE, reason=UNAVAILABLE),
    )


def test_session_without_generator_has_no_configuration_to_keep() -> None:
    item = DefinitionExercise(
        ENTRY, CONTEXT, MCQ, TemplateDistractors(NoGenerator(), (), None)
    )

    record = exercise_record(item)

    assert record.generator is None
    assert record.degradation is DegradationCode.NO_GENERATOR
    assert record.attempts == ()


def test_rejected_exercise_keeps_its_reason() -> None:
    generated = GeneratedDistractors(("speak", "Speak.", "work"))
    item = DefinitionExercise(
        ENTRY,
        CONTEXT,
        MCQ,
        TemplateDistractors(
            ExerciseRejected("hay opciones repetidas", generated),
            (AcceptedAttempt(),),
            SCRIPTED,
        ),
    )

    record = exercise_record(item)

    assert record.degradation is DegradationCode.EXERCISE_REJECTED
    assert record.degradation_reason == "hay opciones repetidas"


def test_plain_cloze_has_no_distractor_source_nor_generator() -> None:
    assert exercise_record(ClozeExercise(ENTRY, CONTEXT, CLOZE)) == ExerciseRecord(
        context=KEY, exercise=CLOZE, source=DistractorSource.NONE
    )


def test_cloze_from_a_degraded_definition_keeps_what_was_tried() -> None:
    """Un `eligible` sin plantilla: es `cloze_original`, pero se pidió al
    generador, y eso se guarda."""
    item = ClozeExercise(
        ENTRY,
        CONTEXT,
        CLOZE,
        definition_fallback=DefinitionFallback(
            RetriesExhausted(), (MalformedAttempt("no es JSON"),) * 3, SCRIPTED
        ),
    )

    record = exercise_record(item)

    assert record.source is DistractorSource.NONE
    assert record.generator == SCRIPTED
    assert record.degradation is DegradationCode.RETRIES_EXHAUSTED
    assert len(record.attempts) == 3
