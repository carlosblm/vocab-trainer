"""Adaptador de importación del vocab.db de Kindle.

Todo lo específico del formato del Kindle vive aquí. El dominio no
conoce estas tablas ni la palabra «Kindle».
"""

import hashlib
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from vocab.ports.importer import RawLookup

QUERY = """
SELECT
    l.id        AS lookup_id,
    w.word      AS word,
    w.stem      AS stem,
    w.lang      AS lang,
    l.usage     AS sentence,
    l.timestamp AS looked_up_ms,
    b.title     AS book_title,
    b.lang      AS book_lang
FROM LOOKUPS l
JOIN WORDS     w ON l.word_key = w.id
JOIN BOOK_INFO b ON l.book_key = b.id
ORDER BY l.timestamp
"""


class KindleVocabImporter:
    """Solo lee un vocab.db de Kindle"""

    def __init__(self, path: Path, langs: tuple[str, ...] = ("en",)) -> None:
        self._path = path
        self._langs = langs

    @property
    def kind(self) -> str:
        return "kindle"

    def checksum(self) -> str:
        h = hashlib.sha256()
        with self._path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def read(self) -> Iterator[RawLookup]:
        # URI de solo lectura: el archivo del usuario nunca se modifica.
        uri = f"file:{self._path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            for row in connection.execute(QUERY):
                if row["lang"] not in self._langs:
                    continue
                if not row["sentence"]:
                    continue
                yield RawLookup(
                    external_id=row["lookup_id"],
                    word=row["word"],
                    lang=row["lang"],
                    sentence=row["sentence"],
                    looked_up_at=datetime.fromtimestamp(
                        row["looked_up_ms"] / 1000, tz=UTC
                    ),
                    source_hint=row["stem"],
                    book_title=row["book_title"],
                    book_lang=row["book_lang"],
                )
        finally:
            connection.close()
