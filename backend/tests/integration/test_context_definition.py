"""La partícula y la decisión de definición de cada contexto llegan a Postgres
(D-033), y reimportar no las cambia (D-012).

Usa el fixture versionado y spaCy real, con léxicos falsos: lo que se prueba es
el camino hasta la base y que no se sobrescribe, no lo que dice OEWN. Lo de OEWN
lo prueban `test_oewn_lexicon` y el test de la exportación de septiembre.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.unit.doubles import FakeLexicon

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.definition_policy import LexiconFacts

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"

FIRST = LexiconFacts(
    pos_supported=False, term_lemmas=frozenset(), senses=(), lexicon="fake:1"
)
# Otra respuesta y otro léxico: si la reimportación tocara lo guardado, cambiarían
# el estado y el léxico de cada contexto.
SECOND = LexiconFacts(
    pos_supported=True, term_lemmas=frozenset(), senses=(), lexicon="fake:2"
)


def _import(session: Session, lexicon: FakeLexicon) -> None:
    import_vocabulary(
        KindleVocabImporter(FIXTURE),
        PostgresVocabularyRepository(session),
        normalize,
        lexicon,
        FIXTURE.name,
    )
    session.flush()


def _stored(session: Session) -> dict[str, tuple[str | None, ...]]:
    rows = session.execute(
        select(
            ContextRow.external_id,
            ContextRow.pos,
            ContextRow.particle,
            ContextRow.definition_status,
            ContextRow.lexicon,
        )
    ).all()
    return {row[0]: tuple(row[1:]) for row in rows if row[0] is not None}


def test_particle_and_decision_reach_postgres(session: Session) -> None:
    """`eased` lleva `out` en la frase del fixture. Cada contexto con
    categoría tiene decisión; uno sin ella, no."""
    _import(session, FakeLexicon(default=FIRST))

    stored = _stored(session)
    particles = {
        session.scalar(
            select(ContextRow.term).where(ContextRow.external_id == key)
        ): particle
        for key, (_, particle, _, _) in stored.items()
        if particle is not None
    }
    assert particles == {"eased": "out"}
    for pos, _, status, lexicon in stored.values():
        if pos is None:
            assert (status, lexicon) == (None, None)
        else:
            assert (status, lexicon) == ("pos_unmapped", "fake:1")


def test_reimport_keeps_the_stored_decisions(session: Session) -> None:
    _import(session, FakeLexicon(default=FIRST))
    before = _stored(session)

    second = FakeLexicon(default=SECOND)
    _import(session, second)

    # El lote entero se evalúa otra vez, y aun así no cambia nada guardado.
    assert second.batches and second.batches[0]
    assert _stored(session) == before
