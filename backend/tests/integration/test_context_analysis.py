"""El análisis de spaCy llega a Postgres por contexto: categoría y rasgos de la
forma consultada en esa frase, no de la entrada.

Usa el fixture versionado (no el vocab.db real) para que corra en CI.
"""

from pathlib import Path

from sqlalchemy import select

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow
from vocab.application.import_vocabulary import import_vocabulary

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"


def test_each_context_row_stores_the_features_of_its_own_form(session):
    """`relied` y `rely` comparten entrada y no forma: un ejercicio de elección
    necesita distractores en pasado para una y en infinitivo para la otra."""
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(FIXTURE), repository, normalize, "vocab_fixture.db"
    )
    session.flush()

    analysis = {
        external_id: (pos, morph)
        for external_id, pos, morph in session.execute(
            select(ContextRow.external_id, ContextRow.pos, ContextRow.morph)
        )
    }

    assert analysis["CR!BOOK1:4"] == ("VERB", "Tense=Past|VerbForm=Fin")
    assert analysis["CR!BOOK1:8"] == ("VERB", "VerbForm=Inf")
    assert analysis["CR!BOOK1:5"] == ("NOUN", "Number=Sing")
