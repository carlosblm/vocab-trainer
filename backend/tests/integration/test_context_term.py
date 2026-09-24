"""Verifica D-020: cada contexto persiste la forma consultada en él, no la de
su entrada.

Usa el fixture versionado (no el vocab.db real) para que corra en CI.
"""

from pathlib import Path

from sqlalchemy import select

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow, EntryRow
from vocab.application.import_vocabulary import import_vocabulary

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"


def test_each_context_row_stores_its_own_form(session):
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(FIXTURE), repository, normalize, "vocab_fixture.db"
    )
    session.flush()

    entry_id, entry_term = session.execute(
        select(EntryRow.id, EntryRow.term).where(
            EntryRow.lemma == "rely", EntryRow.lang == "en"
        )
    ).one()
    term_by_lookup = dict(
        session.execute(
            select(ContextRow.external_id, ContextRow.term).where(
                ContextRow.entry_id == entry_id
            )
        ).all()
    )

    assert entry_term == "relied"
    assert term_by_lookup == {
        "CR!BOOK1:4": "relied",
        "CR!BOOK1:7": "relied",
        "CR!BOOK1:8": "rely",
    }
