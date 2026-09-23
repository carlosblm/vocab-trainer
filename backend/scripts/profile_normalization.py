"""Perfila la normalización sobre `vocab_new.db`, sin base de datos.

Ejecuta el caso de uso real (Kindle → limpieza → spaCy → ruido) contra un
repositorio falso que se queda las entradas en memoria, y compara el
agrupamiento por lema de spaCy contra el dedupe provisional de F0.3 (minúscula
del término consultado). Lee la ruta del archivo de `VOCAB_TEST_DATA`; no se
ejecuta en CI porque ese archivo no se commitea.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from vocab.adapters.kindle import KindleVocabImporter
from vocab.adapters.nlp.normalizer import normalize
from vocab.application.import_vocabulary import import_vocabulary
from vocab.domain.models import Entry, EntryStatus
from vocab.ports.normalizer import CleanedLookup, NormalizedWord
from vocab.ports.repository import ImportStats

load_dotenv()

_data_dir = Path(os.environ["VOCAB_TEST_DATA"]).expanduser()
NEW_DB = _data_dir / "vocab_new.db"


class CapturingRepository:
    """Repositorio falso: retiene las entradas y no persiste nada.

    Permite ejecutar `import_vocabulary` tal cual, en vez de reimplementar
    aquí cómo se agrupan las consultas y se decide su status.
    """

    def __init__(self) -> None:
        self.entries: list[Entry] = []

    def ensure_user(self) -> int:
        return 1

    def register_source(
        self, user_id: int, kind: str, filename: str, checksum: str
    ) -> int:
        return 1

    def upsert_entries(
        self, user_id: int, source_id: int, entries: list[Entry]
    ) -> ImportStats:
        self.entries = entries
        return ImportStats(
            entries_created=len(entries),
            entries_existing=0,
            contexts_created=sum(len(entry.contexts) for entry in entries),
            contexts_existing=0,
        )


class CapturingNormalizer:
    """Envuelve el normalizador real y retiene su salida.

    Evita la segunda pasada de spaCy sobre todo el corpus que hacía la versión
    anterior de este script, que normalizaba una vez para contar y otra dentro
    del caso de uso.
    """

    def __init__(self) -> None:
        self.results: list[NormalizedWord] = []

    def __call__(self, data: list[CleanedLookup]) -> list[NormalizedWord]:
        self.results = normalize(data)
        return self.results


def main() -> None:
    lookups = list(KindleVocabImporter(NEW_DB).read())
    word_by_external_id = {lk.external_id: lk.word for lk in lookups}
    print(f"1. Consultas en inglés procesadas: {len(lookups)}")

    naive_groups = {(lk.word.lower(), lk.lang) for lk in lookups}
    print(
        f"2. Entradas únicas por word.lower() (lema provisional F0.3): "
        f"{len(naive_groups)}"
    )

    repository = CapturingRepository()
    normalizer = CapturingNormalizer()
    import_vocabulary(
        KindleVocabImporter(NEW_DB), repository, normalizer, "vocab_new.db"
    )
    entries = repository.entries

    print(f"3. Entradas únicas por lema de spaCy: {len(entries)}")
    print(f"4. Diferencia (2 − 3): {len(naive_groups) - len(entries)}")

    noise_entries = [entry for entry in entries if entry.status is EntryStatus.NOISE]
    print(f"5. Entradas con status noise: {len(noise_entries)}")
    for entry in noise_entries:
        original_words = sorted(
            {word_by_external_id[c.external_id] for c in entry.contexts}
        )
        print(f"   {entry.lemma} -> {original_words}")

    truncated = sum(
        1 for entry in entries for context in entry.contexts if context.is_truncated
    )
    print(f"6. Contextos con is_truncated = True: {truncated}")

    unresolved = [word for word in normalizer.results if not word.is_resolved]
    print(f"7. Consultas sin token resuelto por el normalizador: {len(unresolved)}")
    for word in unresolved:
        original = word_by_external_id[word.external_id]
        print(f"   {original!r} (external_id={word.external_id})")


if __name__ == "__main__":
    main()
