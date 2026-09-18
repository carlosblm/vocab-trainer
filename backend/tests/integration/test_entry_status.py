"""Verifica D-014: el status de una entrada sobrevive a una reimportación.

Usa el fixture versionado (no el vocab.db real) para que corra en CI.
"""

from pathlib import Path

from sqlalchemy import select, update

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import EntryRow
from vocab.application.import_vocabulary import import_vocabulary

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"


def test_known_status_survives_reimport(session):
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(FIXTURE), repository, normalize, "vocab_fixture.db"
    )
    session.flush()

    session.execute(
        update(EntryRow)
        .where(EntryRow.lemma == "resilient", EntryRow.lang == "en")
        .values(status="known")
    )
    session.flush()

    import_vocabulary(
        KindleVocabImporter(FIXTURE), repository, normalize, "vocab_fixture.db"
    )
    session.flush()

    status = session.scalar(
        select(EntryRow.status).where(
            EntryRow.lemma == "resilient", EntryRow.lang == "en"
        )
    )
    assert status == "known"
