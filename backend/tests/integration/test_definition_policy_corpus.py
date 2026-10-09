"""La política de D-025 sobre la exportación de septiembre de 2026, con el
léxico real y la guarda R1.

Importa el `vocab.db` en el Postgres de testcontainers con la importación real
y lee la misma población que midió D-025: los contextos utilizables de las
entradas `learning`. Se salta si el archivo o el léxico no están; el archivo
no se versiona.

Comprueba dos cosas:

- Sin partícula, los recuentos son los de la tabla de D-025, que midió
  `scripts/measure_definition_source.py`: el adaptador reproduce la medición.
- Con la partícula de R1, lo que cambia está solo en los contextos que marca
  R1, que pasan todos a `LEXICAL_UNIT`. Los recuentos son los medidos, no
  estimados: si cambian el léxico, spaCy o la exportación, hay que volver a
  medir.
"""

import os
from collections import Counter
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.lexicon import OewnLexicon
from vocab.adapters.nlp.lexical_unit import detect_particles
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.cleaning import CleanSentence
from vocab.domain.definition_policy import (
    DefinitionDecision,
    DefinitionStatus,
    decide_definition,
)
from vocab.ports.lexicon import LexiconQuery
from vocab.ports.normalizer import CleanedLookup

load_dotenv()

_data_dir = Path(os.environ.get("VOCAB_TEST_DATA", "")).expanduser()
SEPTEMBER = _data_dir / "vocab_new.db"

pytestmark = pytest.mark.skipif(
    not SEPTEMBER.exists(),
    reason="requiere la exportación de septiembre de 2026, que no se commitea",
)

# La tabla de D-025, con `monosemous` como `ELIGIBLE`.
D025 = {
    DefinitionStatus.POS_UNMAPPED: 40,
    DefinitionStatus.FORM_NOT_FOUND: 44,
    DefinitionStatus.LEMMA_DISAGREES: 27,
    DefinitionStatus.ELIGIBLE: 274,
    DefinitionStatus.POLYSEMOUS: 614,
}
# Medido el 2026-10-07. Los 13 contextos de R1 eran 4 `ELIGIBLE` y 9
# `POLYSEMOUS`, y pasan todos a `LEXICAL_UNIT`.
WITH_R1 = {
    DefinitionStatus.POS_UNMAPPED: 40,
    DefinitionStatus.FORM_NOT_FOUND: 44,
    DefinitionStatus.LEMMA_DISAGREES: 27,
    DefinitionStatus.LEXICAL_UNIT: 13,
    DefinitionStatus.ELIGIBLE: 270,
    DefinitionStatus.POLYSEMOUS: 605,
}


def test_policy_over_september_export(session: Session, lexicon: OewnLexicon) -> None:
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(SEPTEMBER), repository, normalize, SEPTEMBER.name
    )
    session.flush()
    entries = repository.list_learning_entries_with_usable_context(
        repository.ensure_user()
    )
    pairs = [(entry, context) for entry in entries for context in entry.usable_contexts]
    assert len(pairs) == 999

    # La frase vuelve de Postgres como `str` y se reetiqueta: ya pasó por la
    # limpieza al importarse.
    particles = detect_particles(
        [
            CleanedLookup(
                external_id=context.external_id,
                word=context.term,
                lang=entry.lang,
                clean_sentence=CleanSentence(context.clean_sentence),
            )
            for entry, context in pairs
        ]
    )
    marked = {key for key, particle in particles.items() if particle is not None}
    assert len(marked) == 13

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
    # Los hechos no dependen de la partícula: una sola consulta al léxico, y
    # la partícula entra solo en la decisión.
    facts = lexicon.facts(queries)
    with_r1 = {
        q.external_id: decide_definition(
            q.lemma, particles[q.external_id], facts[q.external_id]
        )
        for q in queries
    }
    without_r1 = {
        q.external_id: decide_definition(q.lemma, None, facts[q.external_id])
        for q in queries
    }

    _print_marked(queries, particles, without_r1, with_r1)
    assert Counter(d.status for d in without_r1.values()) == D025
    changed = {key for key in with_r1 if with_r1[key] != without_r1[key]}
    assert changed <= marked
    assert Counter(d.status for d in with_r1.values()) == WITH_R1


def _print_marked(
    queries: list[LexiconQuery],
    particles: dict[str, str | None],
    without_r1: dict[str, DefinitionDecision],
    with_r1: dict[str, DefinitionDecision],
) -> None:
    """Los contextos de R1, antes y después: `pytest -s` para verlos."""
    print("\nterm | partícula | sin R1 | con R1")
    for query in queries:
        key = query.external_id
        if particles[key] is not None:
            print(
                f"  {query.term} | {particles[key]} | {without_r1[key].status} | "
                f"{with_r1[key].status}"
            )
