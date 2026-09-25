"""Verifica D-012: la reimportación es incremental y no duplica nada."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.base import Base
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


def _count(session: Session, table: type[Base]) -> int:
    return session.execute(select(func.count()).select_from(table)).scalar_one()


def _count_truncated(session: Session) -> int:
    return session.execute(
        select(func.count())
        .select_from(ContextRow)
        .where(ContextRow.is_truncated.is_(True))
    ).scalar_one()


def test_reimport_is_incremental(session):
    repository = PostgresVocabularyRepository(session)

    first = import_vocabulary(
        KindleVocabImporter(OLD_DB), repository, normalize, "vocab.db"
    )
    session.flush()

    # Estas cifras dependen del lema que produce spaCy, no de un recuento de
    # palabras en minúsculas: el número de entradas cambiará si cambia el
    # modelo de spaCy o su versión (por ejemplo, "relied" y "rely" se
    # fusionan en el lema "rely"). Que este test falle entonces es correcto:
    # es información sobre el nuevo modelo, no una regresión, y hay que
    # volver a medir y actualizar estos valores, nunca estimarlos.
    assert first.entries_created == 716
    assert first.contexts_created == 845
    assert _count_truncated(session) == 1

    second = import_vocabulary(
        KindleVocabImporter(NEW_DB), repository, normalize, "vocab_new.db"
    )
    session.flush()

    assert second.entries_created == 144
    assert second.entries_existing == 716
    assert second.contexts_created == 179

    assert _count(session, EntryRow) == 860
    assert _count(session, ContextRow) == 1024
    assert _count(session, SourceRow) == 2


def test_reimporting_same_file_creates_nothing(session):
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(KindleVocabImporter(OLD_DB), repository, normalize, "vocab.db")
    session.flush()

    again = import_vocabulary(
        KindleVocabImporter(OLD_DB), repository, normalize, "vocab.db"
    )
    assert again.entries_created == 0
    assert again.contexts_created == 0
    assert _count(session, SourceRow) == 1
