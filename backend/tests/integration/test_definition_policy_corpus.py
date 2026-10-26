"""La política de D-025 sobre la exportación de septiembre de 2026, guardada al
importar (D-033) y leída de la base.

Importa el `vocab.db` en el Postgres de testcontainers con el caso de uso real:
spaCy, la guarda R1 y el léxico OEWN. Se salta si el archivo o el léxico no
están; el archivo no se versiona.

Comprueba tres cosas:

- Sobre los contextos que lee `study`, los recuentos son los de D-032.
- Sin partícula, los mismos hechos reproducen la tabla de D-025, que midió
  `scripts/measure_definition_source.py`: el adaptador reproduce la medición.
- Lo que cambia por R1 está solo en los contextos que marca, que pasan todos a
  `LEXICAL_UNIT`.

Los recuentos son los medidos, no estimados: si cambian el léxico, spaCy o la
exportación, hay que volver a medir.
"""

import os
from collections import Counter
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.lexicon import OewnLexicon
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.definition_policy import DefinitionStatus, decide_definition
from vocab.ports.lexicon import LexiconQuery

load_dotenv()

_data_dir = Path(os.environ.get("VOCAB_TEST_DATA", "")).expanduser()
SEPTEMBER = _data_dir / "vocab_new.db"

pytestmark = pytest.mark.skipif(
    not SEPTEMBER.exists(),
    reason="requiere la exportación de septiembre de 2026, que no se commitea",
)

# D-032, sobre los 999 contextos utilizables de entradas `learning`.
D032 = {
    DefinitionStatus.POS_UNMAPPED: 40,
    DefinitionStatus.FORM_NOT_FOUND: 44,
    DefinitionStatus.LEMMA_DISAGREES: 27,
    DefinitionStatus.LEXICAL_UNIT: 13,
    DefinitionStatus.ELIGIBLE: 270,
    DefinitionStatus.POLYSEMOUS: 605,
}
# Todos los contextos importados, también los truncados y los de entradas
# `noise`. Medido el 2026-10-26. `None` son los 2 que spaCy no localizó (D-016):
# no se evalúan.
ALL_CONTEXTS = {
    None: 2,
    "pos_unmapped": 61,
    "form_not_found": 44,
    "lemma_disagrees": 27,
    "lexical_unit": 13,
    "eligible": 271,
    "polysemous": 606,
}
# La tabla de D-025, sin partícula, con `monosemous` como `ELIGIBLE`.
D025 = {
    DefinitionStatus.POS_UNMAPPED: 40,
    DefinitionStatus.FORM_NOT_FOUND: 44,
    DefinitionStatus.LEMMA_DISAGREES: 27,
    DefinitionStatus.ELIGIBLE: 274,
    DefinitionStatus.POLYSEMOUS: 614,
}


def test_policy_over_september_export(session: Session, lexicon: OewnLexicon) -> None:
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(SEPTEMBER), repository, normalize, lexicon, SEPTEMBER.name
    )
    session.flush()

    entries = repository.list_learning_entries_with_usable_context(
        repository.ensure_user()
    )
    pairs = [(entry, context) for entry in entries for context in entry.usable_contexts]
    assert len(pairs) == 999
    # Ninguno de los 999 se quedó sin evaluar: todos tienen categoría.
    stored = {
        context.external_id: context.definition
        for _, context in pairs
        if context.definition is not None
    }
    assert len(stored) == 999
    assert Counter(decision.status for decision in stored.values()) == D032

    marked = {context.external_id for _, context in pairs if context.particle}
    assert len(marked) == 13

    # Los mismos hechos, sin partícula: la medición de D-025.
    queries = [
        LexiconQuery(
            external_id=context.external_id,
            term=context.term,
            lemma=entry.lemma,
            pos=context.pos,
            lang=entry.lang,
        )
        for entry, context in pairs
    ]
    facts = lexicon.facts(queries)
    without_r1 = {
        q.external_id: decide_definition(q.lemma, None, facts[q.external_id])
        for q in queries
    }
    assert Counter(d.status for d in without_r1.values()) == D025
    changed = {key for key in stored if stored[key] != without_r1[key]}
    assert changed <= marked
    assert {stored[key].status for key in marked} == {DefinitionStatus.LEXICAL_UNIT}

    rows = session.execute(
        select(ContextRow.definition_status, func.count()).group_by(
            ContextRow.definition_status
        )
    ).all()
    assert {status: count for status, count in rows} == ALL_CONTEXTS
