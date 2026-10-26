"""Cobertura de la plantilla de degradación (§7.3) sobre la exportación de
septiembre de 2026: de los contextos `eligible` de `study`, cuántos tienen tres
distractores del propio vocabulario y cuántos irían a `cloze_original`.

Importa con el caso de uso real (spaCy, R1 y OEWN) en el Postgres de
testcontainers y lee los candidatos con la lectura real del repositorio. Se
salta si el archivo o el léxico no están.

Que haya plantilla no depende del azar: la plantilla devuelve `None` solo si
no existen tres distractores válidos. Los recuentos son los medidos.
"""

import os
import random
from collections import Counter
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.lexicon import OewnLexicon
from vocab.adapters.nlp.normalizer import normalize
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.definition_policy import DefinitionStatus
from vocab.domain.exercises.definition_template import choose_template_distractors
from vocab.domain.exercises.mcq_definition import McqDefinition

load_dotenv()

_data_dir = Path(os.environ.get("VOCAB_TEST_DATA", "")).expanduser()
SEPTEMBER = _data_dir / "vocab_new.db"

pytestmark = pytest.mark.skipif(
    not SEPTEMBER.exists(),
    reason="requiere la exportación de septiembre de 2026, que no se commitea",
)


def test_template_coverage_over_september_export(
    session: Session, lexicon: OewnLexicon
) -> None:
    repository = PostgresVocabularyRepository(session)
    import_vocabulary(
        KindleVocabImporter(SEPTEMBER), repository, normalize, lexicon, SEPTEMBER.name
    )
    session.flush()
    user_id = repository.ensure_user()
    entries = repository.list_learning_entries_with_usable_context(user_id)
    candidates = repository.list_definition_candidates(user_id)

    eligible = [
        (entry, context)
        for entry in entries
        for context in entry.usable_contexts
        if context.definition is not None
        and context.definition.status is DefinitionStatus.ELIGIBLE
    ]
    assert len(eligible) == 270

    covered: Counter[str] = Counter()
    uncovered: Counter[str] = Counter()
    rng = random.Random(20261026)
    for entry, context in eligible:
        assert context.pos is not None and context.definition is not None
        distractors = choose_template_distractors(entry, context, candidates, rng)
        if distractors is None:
            uncovered[context.pos] += 1
            continue
        covered[context.pos] += 1
        # Las invariantes del ejercicio se cumplen con datos reales.
        assert context.definition.definition is not None
        McqDefinition.new(
            context.clean_sentence,
            context.term,
            context.definition.definition,
            distractors,
            rng,
        )

    # Medido el 2026-10-26: todos tienen plantilla.
    assert len(candidates) == 270
    assert covered == {"NOUN": 151, "ADJ": 50, "VERB": 47, "ADV": 22}
    assert uncovered == {}
