"""Implementación del repositorio sobre PostgreSQL."""

from collections import defaultdict

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vocab.adapters.postgres.tables import ContextRow, EntryRow, SourceRow, UserRow
from vocab.domain.models import Context, Entry, EntryStatus
from vocab.ports.repository import ImportStats


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
                        book_title=context.book_title,
                        book_lang=context.book_lang,
                        captured_at=context.captured_at,
                    )
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
    )
