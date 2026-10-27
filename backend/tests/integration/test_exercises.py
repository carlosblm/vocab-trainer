"""Los ejercicios guardados y las marcas «la definición no encaja», contra el
Postgres de testcontainers.

La ida y vuelta pasa por el adaptador real: lo que se guarda se reconstruye con
los constructores del dominio y del puerto, así que sus invariantes se
comprueban también al leer.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import DefinitionFlagRow, ExerciseRow
from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.distractor_validation import Violation, ViolationCode
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import Context, ContextKey, DefinitionFlag, Entry
from vocab.ports.distractor_generator import GeneratorIdentity
from vocab.ports.exercise_record import (
    AttemptOutcome,
    AttemptRecord,
    DegradationCode,
    DistractorSource,
    ExerciseRecord,
)

SENTENCE = "They sojourned in the hills."
SOJOURN = "spend a certain length of time; reside temporarily"
KEY = ContextKey(lemma="sojourn", lang="en", external_id="s1")
SCRIPTED = GeneratorIdentity("scripted", "test")
UNAVAILABLE = "Ollama en http://localhost:1/api/chat: no se pudo conectar"
MCQ = McqDefinition(
    SENTENCE,
    "sojourned",
    SOJOURN,
    ("travel quickly", SOJOURN, "speak quietly", "work hard"),
)


@pytest.fixture
def repository(session: Session) -> PostgresVocabularyRepository:
    """El repositorio con una entrada `eligible`, `sojourn`, y su contexto."""
    repository = PostgresVocabularyRepository(session)
    user_id = repository.ensure_user()
    source_id = repository.register_source(user_id, "test", "test", "sum")
    context = Context(
        external_id=KEY.external_id,
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
    entry = Entry(term="sojourned", lemma="sojourn", lang="en", contexts=[context])
    repository.upsert_entries(user_id, source_id, [entry])
    return repository


@pytest.mark.parametrize(
    "record",
    [
        # Del modelo, con un intento rechazado antes del aceptado.
        ExerciseRecord(
            context=KEY,
            exercise=MCQ,
            source=DistractorSource.MODEL,
            generator=SCRIPTED,
            attempts=(
                AttemptRecord(
                    AttemptOutcome.REJECTED,
                    distractors=("not stay", "stay", "leave"),
                    violations=(
                        Violation(ViolationCode.NEGATION, 0),
                        Violation(ViolationCode.OVERLAPS_CORRECT, 1),
                    ),
                ),
                AttemptRecord(AttemptOutcome.ACCEPTED),
            ),
        ),
        # De la plantilla, sin generador en la sesión.
        ExerciseRecord(
            context=KEY,
            exercise=MCQ,
            source=DistractorSource.TEMPLATE,
            degradation=DegradationCode.NO_GENERATOR,
        ),
        # Hueco, en la variante de elección y en la de escritura.
        ExerciseRecord(
            context=KEY,
            exercise=ClozeOriginalChoice(
                ClozeOriginal(SENTENCE, "sojourned"),
                ("tossed", "sojourned", "eased", "waned"),
            ),
            source=DistractorSource.NONE,
        ),
        ExerciseRecord(
            context=KEY,
            exercise=ClozeOriginal(SENTENCE, "sojourned"),
            source=DistractorSource.NONE,
        ),
    ],
    ids=["model", "template", "cloze_choice", "cloze_writing"],
)
def test_saved_exercise_comes_back_the_same(
    repository: PostgresVocabularyRepository, record: ExerciseRecord
) -> None:
    exercise_id = repository.save_exercise(repository.ensure_user(), record)

    stored = repository.load_exercise(exercise_id)

    assert stored.id == exercise_id
    assert stored.record == record
    assert stored.created_at is not None


def test_degradation_saves_the_generator_it_was_tried_with(
    repository: PostgresVocabularyRepository, session: Session
) -> None:
    """En las columnas, para que una consulta vea con qué modelo y qué prompt
    degradó, y el motivo."""
    record = ExerciseRecord(
        context=KEY,
        exercise=MCQ,
        source=DistractorSource.TEMPLATE,
        generator=SCRIPTED,
        attempts=(AttemptRecord(AttemptOutcome.UNAVAILABLE, reason=UNAVAILABLE),),
        degradation=DegradationCode.PROVIDER_UNAVAILABLE,
        degradation_reason=UNAVAILABLE,
    )

    exercise_id = repository.save_exercise(repository.ensure_user(), record)

    row = session.get_one(ExerciseRow, exercise_id)
    assert (row.model, row.prompt_version) == ("scripted", "test")
    assert (row.distractor_source, row.degradation_cause) == (
        "template",
        "provider_unavailable",
    )
    assert row.attempts == [{"outcome": "unavailable", "reason": UNAVAILABLE}]
    assert repository.load_exercise(exercise_id).record == record


def test_flags_are_saved_once_and_read_back(
    repository: PostgresVocabularyRepository, session: Session
) -> None:
    user_id = repository.ensure_user()
    flag = DefinitionFlag(context=KEY, sense_id="sojourn-v-1", lexicon="oewn:2025")

    repository.save_definition_flag(user_id, flag)
    repository.save_definition_flag(user_id, flag)

    assert repository.list_definition_flags(user_id) == frozenset({flag})
    assert session.scalar(select(func.count()).select_from(DefinitionFlagRow)) == 1
