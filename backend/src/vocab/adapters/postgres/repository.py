"""Implementación del repositorio sobre PostgreSQL."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vocab.adapters.postgres.tables import (
    ContextRow,
    DefinitionFlagRow,
    EntryRow,
    ExerciseRow,
    SourceRow,
    UserRow,
)
from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.distractor_validation import Violation, ViolationCode
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.domain.exercises.definition_template import DefinitionCandidate
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import (
    Context,
    ContextKey,
    DefinitionFlag,
    Entry,
    EntryStatus,
)
from vocab.ports.distractor_generator import GeneratorIdentity
from vocab.ports.exercise_record import (
    AttemptOutcome,
    AttemptRecord,
    DegradationCode,
    DistractorSource,
    Exercise,
    ExerciseKind,
    ExerciseRecord,
)
from vocab.ports.repository import ImportStats


@dataclass(frozen=True)
class StoredExercise:
    """Un ejercicio leído de la base: su id, su registro y cuándo se guardó.

    Solo lo lee este adaptador: ningún caso de uso lee todavía ejercicios
    guardados. Los leerán los repasos de F3.
    """

    id: int
    record: ExerciseRecord
    created_at: datetime


class PostgresVocabularyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_user(self) -> int:
        user_id = self._session.scalar(select(UserRow.id).limit(1))
        if user_id is None:
            user = UserRow()
            self._session.add(user)
            self._session.flush()
            user_id = user.id
        return user_id

    def register_source(
        self, user_id: int, kind: str, filename: str, checksum: str
    ) -> int:
        # Un archivo que ha crecido tiene otro checksum y es una fuente nueva.
        # Reimportar el mismo archivo reutiliza la fila existente (D-012).
        statement = (
            insert(SourceRow)
            .values(user_id=user_id, kind=kind, filename=filename, checksum=checksum)
            .on_conflict_do_nothing(index_elements=["user_id", "checksum"])
            .returning(SourceRow.id)
        )
        source_id = self._session.scalar(statement)
        if source_id is None:
            source_id = self._session.scalar(
                select(SourceRow.id).where(
                    SourceRow.user_id == user_id,
                    SourceRow.checksum == checksum,
                )
            )
        assert source_id is not None, "la fuente debe existir tras el insert"
        return source_id

    def upsert_entries(
        self, user_id: int, source_id: int, entries: list[Entry]
    ) -> ImportStats:
        entries_created = contexts_created = 0
        total_contexts = 0

        for entry in entries:
            entry_statement = (
                insert(EntryRow)
                .values(
                    user_id=user_id,
                    source_id=source_id,
                    external_id=entry.external_id,
                    term=entry.term,
                    lemma=entry.lemma,
                    lang=entry.lang,
                    status=entry.status.value,
                    first_seen_at=entry.first_seen_at,
                )
                .on_conflict_do_nothing(index_elements=["user_id", "lemma", "lang"])
                .returning(EntryRow.id)
            )
            entry_id = self._session.scalar(entry_statement)

            if entry_id is not None:
                entries_created += 1
            else:
                entry_id = self._session.scalar(
                    select(EntryRow.id).where(
                        EntryRow.user_id == user_id,
                        EntryRow.lemma == entry.lemma,
                        EntryRow.lang == entry.lang,
                    )
                )

            for context in entry.contexts:
                total_contexts += 1
                context_statement = (
                    insert(ContextRow)
                    .values(
                        entry_id=entry_id,
                        external_id=context.external_id,
                        term=context.term,
                        raw_sentence=context.raw_sentence,
                        clean_sentence=context.clean_sentence,
                        is_truncated=context.is_truncated,
                        pos=context.pos,
                        morph=context.morph,
                        particle=context.particle,
                        **_definition_columns(context.definition),
                        book_title=context.book_title,
                        book_lang=context.book_lang,
                        captured_at=context.captured_at,
                    )
                    # Un contexto ya guardado conserva su decisión aunque el
                    # lote traiga otra: la reimportación no toca nada (D-012).
                    .on_conflict_do_nothing(index_elements=["entry_id", "external_id"])
                    .returning(ContextRow.id)
                )
                if self._session.scalar(context_statement) is not None:
                    contexts_created += 1

        return ImportStats(
            entries_created=entries_created,
            entries_existing=len(entries) - entries_created,
            contexts_created=contexts_created,
            contexts_existing=total_contexts - contexts_created,
        )

    def list_learning_entries_with_usable_context(self, user_id: int) -> list[Entry]:
        # El estado se filtra en SQL: es un criterio de consulta. Si un
        # contexto es utilizable lo decide el dominio (`Context.is_usable`) y
        # no se repite aquí: dos copias de la regla acabarían divergiendo. El
        # coste es traer también los contextos truncados, que son pocos.
        entries = self._load_entries(
            user_id, EntryRow.status == EntryStatus.LEARNING.value
        )
        return [entry for entry in entries if entry.usable_contexts]

    def list_non_noise_entries(self, user_id: int) -> list[Entry]:
        # `!= noise` y no `IN (learning, known)`: un estado nuevo que se añada
        # al CHECK aportará distractores salvo que alguien decida lo contrario.
        return self._load_entries(user_id, EntryRow.status != EntryStatus.NOISE.value)

    def list_definition_candidates(self, user_id: int) -> list[DefinitionCandidate]:
        # Una consulta, solo con las columnas que la plantilla usa: no hace
        # falta reconstruir las entradas enteras.
        rows = self._session.execute(
            select(
                EntryRow.lemma,
                EntryRow.lang,
                ContextRow.pos,
                ContextRow.sense_id,
                ContextRow.definition,
            )
            .join(ContextRow, ContextRow.entry_id == EntryRow.id)
            .where(
                EntryRow.user_id == user_id,
                EntryRow.status != EntryStatus.NOISE.value,
                ContextRow.definition_status == DefinitionStatus.ELIGIBLE.value,
            )
            .order_by(EntryRow.id, ContextRow.id)
        ).tuples()
        candidates = []
        for lemma, lang, pos, sense_id, definition in rows:
            # Un contexto evaluado tiene categoría, y uno `eligible`, definición
            # y sentido (CHECK de la tabla); los asserts se lo dicen a mypy.
            assert pos is not None and sense_id is not None and definition is not None
            candidates.append(
                DefinitionCandidate(
                    lemma=lemma,
                    lang=lang,
                    pos=pos,
                    sense_id=sense_id,
                    definition=definition,
                )
            )
        return candidates

    def list_definition_flags(self, user_id: int) -> frozenset[DefinitionFlag]:
        rows = self._session.execute(
            select(
                EntryRow.lemma,
                EntryRow.lang,
                ContextRow.external_id,
                DefinitionFlagRow.sense_id,
                DefinitionFlagRow.lexicon,
            )
            .join(ContextRow, ContextRow.entry_id == EntryRow.id)
            .join(DefinitionFlagRow, DefinitionFlagRow.context_id == ContextRow.id)
            .where(EntryRow.user_id == user_id)
        ).tuples()
        flags = set()
        for lemma, lang, external_id, sense_id, lexicon in rows:
            assert external_id is not None, "todo contexto importado tiene external_id"
            flags.add(
                DefinitionFlag(
                    context=ContextKey(lemma=lemma, lang=lang, external_id=external_id),
                    sense_id=sense_id,
                    lexicon=lexicon,
                )
            )
        return frozenset(flags)

    def save_exercise(self, user_id: int, record: ExerciseRecord) -> int:
        entry_id, context_id = self._context_ids(user_id, record.context)
        generator = record.generator
        statement = (
            insert(ExerciseRow)
            .values(
                entry_id=entry_id,
                context_id=context_id,
                kind=record.kind.value,
                lang=record.context.lang,
                payload=_payload(record.exercise),
                distractor_source=record.source.value,
                model=generator.model if generator else None,
                prompt_version=generator.prompt_version if generator else None,
                attempts=[_attempt_json(attempt) for attempt in record.attempts],
                degradation_cause=(
                    record.degradation.value if record.degradation else None
                ),
                degradation_reason=record.degradation_reason,
            )
            .returning(ExerciseRow.id)
        )
        exercise_id = self._session.scalar(statement)
        assert exercise_id is not None, "un INSERT sin conflicto devuelve su id"
        return exercise_id

    def save_definition_flag(self, user_id: int, flag: DefinitionFlag) -> None:
        _, context_id = self._context_ids(user_id, flag.context)
        self._session.execute(
            insert(DefinitionFlagRow)
            .values(context_id=context_id, sense_id=flag.sense_id, lexicon=flag.lexicon)
            .on_conflict_do_nothing(
                index_elements=["context_id", "sense_id", "lexicon"]
            )
        )

    def load_exercise(self, exercise_id: int) -> StoredExercise:
        """El ejercicio guardado con ese id, reconstruido con los tipos del
        dominio y del puerto: sus invariantes se comprueban también al leer."""
        row, lemma, lang, external_id = self._session.execute(
            select(ExerciseRow, EntryRow.lemma, EntryRow.lang, ContextRow.external_id)
            .join(ContextRow, ContextRow.id == ExerciseRow.context_id)
            .join(EntryRow, EntryRow.id == ExerciseRow.entry_id)
            .where(ExerciseRow.id == exercise_id)
        ).one()
        assert external_id is not None, "todo contexto importado tiene external_id"
        generator = (
            GeneratorIdentity(row.model, row.prompt_version)
            if row.model is not None and row.prompt_version is not None
            else None
        )
        record = ExerciseRecord(
            context=ContextKey(lemma=lemma, lang=lang, external_id=external_id),
            exercise=_exercise_from_payload(ExerciseKind(row.kind), row.payload),
            source=DistractorSource(row.distractor_source),
            generator=generator,
            attempts=tuple(_attempt_from_json(item) for item in row.attempts),
            degradation=(
                DegradationCode(row.degradation_cause)
                if row.degradation_cause is not None
                else None
            ),
            degradation_reason=row.degradation_reason,
        )
        return StoredExercise(id=row.id, record=record, created_at=row.created_at)

    def _context_ids(self, user_id: int, key: ContextKey) -> tuple[int, int]:
        """Los ids de la entrada y del contexto de `key`. Que no exista es un
        error de quien llama, y `one` lo dice."""
        entry_id, context_id = (
            self._session.execute(
                select(EntryRow.id, ContextRow.id)
                .join(ContextRow, ContextRow.entry_id == EntryRow.id)
                .where(
                    EntryRow.user_id == user_id,
                    EntryRow.lemma == key.lemma,
                    EntryRow.lang == key.lang,
                    ContextRow.external_id == key.external_id,
                )
            )
            .tuples()
            .one()
        )
        return entry_id, context_id

    def _load_entries(
        self, user_id: int, status_filter: ColumnElement[bool]
    ) -> list[Entry]:
        """Entradas del usuario que pasan el filtro, con todos sus contextos.

        Una sola consulta con join, no una por entrada. El `order_by` hace el
        orden estable que prometen las lecturas del puerto.
        """
        rows = self._session.execute(
            select(EntryRow, ContextRow)
            .join(ContextRow, ContextRow.entry_id == EntryRow.id)
            .where(EntryRow.user_id == user_id, status_filter)
            .order_by(EntryRow.id, ContextRow.id)
        ).tuples()

        entry_rows: dict[int, EntryRow] = {}
        contexts_by_entry: dict[int, list[Context]] = defaultdict(list)
        for entry_row, context_row in rows:
            entry_rows[entry_row.id] = entry_row
            contexts_by_entry[entry_row.id].append(_context_from_row(context_row))

        return [
            _entry_from_row(entry_row, contexts_by_entry[entry_id])
            for entry_id, entry_row in entry_rows.items()
        ]


def _entry_from_row(row: EntryRow, contexts: list[Context]) -> Entry:
    """Reconstruye con el constructor normal, no con `Entry.new`: el estado es
    el que está guardado, y puede ser el que puso el usuario (D-018)."""
    return Entry(
        term=row.term,
        lemma=row.lemma,
        lang=row.lang,
        external_id=row.external_id,
        status=EntryStatus(row.status),
        contexts=contexts,
    )


def _context_from_row(row: ContextRow) -> Context:
    # La tabla admite NULL en dos columnas que el dominio no admite; la
    # ingesta escribe siempre las dos. Sin frase limpia no hay ejercicio, así
    # que `""` la traduce a «no utilizable». Un `external_id` no tiene valor
    # por defecto con sentido: si falta, es un error de datos y se dice.
    assert row.external_id is not None, "todo contexto importado tiene external_id"
    return Context(
        external_id=row.external_id,
        term=row.term,
        raw_sentence=row.raw_sentence,
        clean_sentence=row.clean_sentence or "",
        is_truncated=row.is_truncated,
        captured_at=row.captured_at,
        pos=row.pos,
        morph=row.morph,
        book_title=row.book_title,
        book_lang=row.book_lang,
        particle=row.particle,
        definition=_definition_from_row(row),
    )


def _definition_columns(decision: DefinitionDecision | None) -> dict[str, str | None]:
    """La decisión en sus cuatro columnas; todas `NULL` si no se evaluó."""
    if decision is None:
        return {
            "definition_status": None,
            "definition": None,
            "sense_id": None,
            "lexicon": None,
        }
    return {
        "definition_status": decision.status.value,
        "definition": decision.definition,
        "sense_id": decision.sense_id,
        "lexicon": decision.lexicon,
    }


def _definition_from_row(row: ContextRow) -> DefinitionDecision | None:
    """La decisión guardada, o `None` si el contexto no se evaluó.

    Pasa otra vez por `DefinitionDecision`, así que su invariante también se
    comprueba al leer, no solo con las CHECK de la tabla.
    """
    if row.definition_status is None:
        return None
    # La CHECK `lexicon_with_status` lo garantiza; el assert se lo dice a mypy.
    assert row.lexicon is not None, "un contexto evaluado tiene léxico"
    return DefinitionDecision(
        DefinitionStatus(row.definition_status),
        row.lexicon,
        definition=row.definition,
        sense_id=row.sense_id,
    )


def _payload(exercise: Exercise) -> dict[str, Any]:
    """Lo que hace falta para reconstruir el ejercicio. La respuesta es el
    campo del que se reconstruye, no su posición: guardar el índice sería una
    segunda copia que podría no cuadrar con las opciones."""
    if isinstance(exercise, McqDefinition):
        return {
            "sentence": exercise.sentence,
            "word": exercise.word,
            "definition": exercise.definition,
            "options": list(exercise.options),
        }
    if isinstance(exercise, ClozeOriginalChoice):
        cloze = exercise.cloze
        options: list[str] | None = list(exercise.options)
    else:
        cloze = exercise
        options = None
    return {"sentence": cloze.sentence, "word": cloze.word, "options": options}


def _exercise_from_payload(kind: ExerciseKind, payload: dict[str, Any]) -> Exercise:
    """El ejercicio, por su constructor: sus invariantes se comprueban al leer."""
    if kind is ExerciseKind.MCQ_DEFINITION:
        return McqDefinition(
            sentence=payload["sentence"],
            word=payload["word"],
            definition=payload["definition"],
            options=tuple(payload["options"]),
        )
    cloze = ClozeOriginal(sentence=payload["sentence"], word=payload["word"])
    if payload["options"] is None:
        return cloze
    return ClozeOriginalChoice(cloze=cloze, options=tuple(payload["options"]))


def _attempt_json(attempt: AttemptRecord) -> dict[str, Any]:
    """El intento con solo los campos que tiene: un `null` de más no dice
    nada al leerlo en la base."""
    data: dict[str, Any] = {"outcome": attempt.outcome.value}
    if attempt.distractors is not None:
        data["distractors"] = list(attempt.distractors)
    if attempt.violations:
        data["violations"] = [
            {
                "code": violation.code.value,
                "distractor_index": violation.distractor_index,
            }
            for violation in attempt.violations
        ]
    if attempt.reason is not None:
        data["reason"] = attempt.reason
    return data


def _attempt_from_json(data: dict[str, Any]) -> AttemptRecord:
    distractors = data.get("distractors")
    if distractors is not None:
        first, second, third = distractors
        distractors = (first, second, third)
    return AttemptRecord(
        outcome=AttemptOutcome(data["outcome"]),
        distractors=distractors,
        violations=tuple(
            Violation(ViolationCode(item["code"]), item["distractor_index"])
            for item in data.get("violations", [])
        ),
        reason=data.get("reason"),
    )
