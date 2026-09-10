"""Verifica D-012: la reimportación es incremental y no duplica nada."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import func, select

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow, EntryRow, SourceRow
from vocab.application.import_vocabulary import import_vocabulary

load_dotenv()

_data_dir = Path(os.environ.get("VOCAB_TEST_DATA", "")).expanduser()
OLD_DB = _data_dir / "vocab.db"
NEW_DB = _data_dir / "vocab_new.db"

pytestmark = pytest.mark.skipif(
    not (OLD_DB.exists() and NEW_DB.exists()),
    reason="requiere los vocab.db reales, que no se commitean",
)


def _count(session, table) -> int:
    return session.scalar(select(func.count()).select_from(table))


def test_reimport_is_incremental(session):
    repository = PostgresVocabularyRepository(session)

    first = import_vocabulary(KindleVocabImporter(OLD_DB), repository, "vocab.db")
    session.flush()
    assert first.entries_created == 745
    assert first.contexts_created == 845

    second = import_vocabulary(KindleVocabImporter(NEW_DB), repository, "vocab_new.db")
    session.flush()

    assert second.entries_created == 159
    assert second.entries_existing == 745
    assert second.contexts_created == 179

    assert _count(session, EntryRow) == 904
    assert _count(session, ContextRow) == 1024
    assert _count(session, SourceRow) == 2


def test_reimporting_same_file_creates_nothing(session):
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(KindleVocabImporter(OLD_DB), repository, "vocab.db")
    session.flush()

    again = import_vocabulary(KindleVocabImporter(OLD_DB), repository, "vocab.db")
    assert again.entries_created == 0
    assert again.contexts_created == 0
    assert _count(session, SourceRow) == 1
