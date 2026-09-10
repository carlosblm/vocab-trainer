"""Implementación del repositorio sobre PostgreSQL."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vocab.adapters.postgres.tables import ContextRow, EntryRow, SourceRow, UserRow
from vocab.domain.models import Entry
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
                    pos=entry.pos,
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
                        raw_sentence=context.raw_sentence,
                        clean_sentence=context.clean_sentence,
                        is_truncated=context.is_truncated,
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
