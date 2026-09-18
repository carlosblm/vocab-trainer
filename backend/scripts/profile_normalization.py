"""Perfila la normalización sobre `vocab_new.db`, sin base de datos.

Ejecuta el mismo pipeline que `import_vocabulary` (Kindle → limpieza →
spaCy → ruido) y compara el agrupamiento por lema real de spaCy contra el
dedupe provisional de F0.3 (minúscula del término consultado). Lee la ruta
del archivo de `VOCAB_TEST_DATA`; no se ejecuta en CI porque ese archivo no
se commitea.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.cleaning import clean_sentence, is_truncated
from vocab.adapters.nlp.normalizer import CleanedLookup, normalize
from vocab.application.import_vocabulary import _build_entries
from vocab.domain.models import EntryStatus

load_dotenv()

_data_dir = Path(os.environ["VOCAB_TEST_DATA"]).expanduser()
NEW_DB = _data_dir / "vocab_new.db"


def main() -> None:
    lookups = list(KindleVocabImporter(NEW_DB).read())
    word_by_external_id = {lk.external_id: lk.word for lk in lookups}
    print(f"1. Consultas en inglés procesadas: {len(lookups)}")

    naive_groups = {(lk.word.lower(), lk.lang) for lk in lookups}
    print(
        f"2. Entradas únicas por word.lower() (lema provisional F0.3): "
        f"{len(naive_groups)}"
    )

    cleaned_lookups = [CleanedLookup(clean_sentence(lk.sentence), lk) for lk in lookups]
    normalized = normalize(cleaned_lookups)

    spacy_groups = {(word.lemma, lk.lang) for lk, word in normalized}
    print(f"3. Entradas únicas por lema de spaCy: {len(spacy_groups)}")
    print(f"4. Diferencia (2 − 3): {len(naive_groups) - len(spacy_groups)}")

    # Reutiliza la función de producción: es la única fuente de verdad de
    # cómo se agrupan las consultas en entradas y se decide su status.
    entries = _build_entries(lookups, normalize)
    noise_entries = [entry for entry in entries if entry.status is EntryStatus.NOISE]
    print(f"5. Entradas con status noise: {len(noise_entries)}")
    for entry in noise_entries:
        original_words = sorted(
            {word_by_external_id[c.external_id] for c in entry.contexts}
        )
        print(f"   {entry.lemma} -> {original_words}")

    truncated = sum(1 for item in cleaned_lookups if is_truncated(item.clean_sentence))
    print(f"6. Contextos con is_truncated = True: {truncated}")

    unresolved = [(lk, word) for lk, word in normalized if not word.is_resolved]
    print(f"7. Consultas sin token resuelto por el normalizador: {len(unresolved)}")
    for lookup, _ in unresolved:
        print(f"   {lookup.word!r} (external_id={lookup.external_id})")


if __name__ == "__main__":
    main()
