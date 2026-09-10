"""Construye un vocab.db mínimo con los casos difíciles del corpus real."""

import sqlite3
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "vocab_fixture.db"

SCHEMA = """
CREATE TABLE WORDS (
  id TEXT PRIMARY KEY NOT NULL, word TEXT, stem TEXT, lang TEXT,
  category INTEGER DEFAULT 0, timestamp INTEGER DEFAULT 0, profileid TEXT);
CREATE TABLE LOOKUPS (
  id TEXT PRIMARY KEY NOT NULL, word_key TEXT, book_key TEXT, dict_key TEXT,
  pos TEXT, usage TEXT, timestamp INTEGER DEFAULT 0);
CREATE TABLE BOOK_INFO (
  id TEXT PRIMARY KEY NOT NULL, asin TEXT, guid TEXT,
  lang TEXT, title TEXT, authors TEXT);
"""

BOOKS = [
    ("CR!BOOK1", "ASIN1", "CR!BOOK1", "en", "  A_Test_Book ", "Test Author"),
    ("CR!BOOK2", "ASIN2", "CR!BOOK2", "es", "Otro Libro", "Autora Dos"),
]

# (word_id, word, stem, lang, ts_words)
WORDS = [
    ("en:resilient", "resilient", "resilient", "en", 1_700_000_000_000),
    ("en:eased", "eased", "ease", "en", 1_700_000_100_000),
    ("en:relied", "relied", "rely", "en", 1_700_000_200_000),
    ("en:stake", "stake", "stake", "en", 1_700_000_300_000),
    ("en:brow", "brow", "brow ()", "en", 1_700_000_400_000),
    ("es:salvo", "Salvo", "salvo", "es", 1_700_000_500_000),
]

# (lookup_id, word_key, book_key, usage, ts)  — ts crecientes por palabra
LOOKUPS = [
    # caso normal, con espacios sobrantes (98,5 % del corpus real)
    (
        "CR!BOOK1:1",
        "en:resilient",
        " The bridge proved resilient after the flood. ",
        1_700_000_000_000,
    ),
    # misma palabra, segundo contexto: prueba la relación 1-N
    (
        "CR!BOOK1:2",
        "en:resilient",
        "Resilient materials absorb impact without cracking.",
        1_700_000_050_000,
    ),
    # unidad léxica: el significado no está en la palabra (D-008)
    (
        "CR!BOOK1:3",
        "en:eased",
        "Electronics eased out hydraulics in the new design.",
        1_700_000_100_000,
    ),
    # lema distinto de la palabra: prueba la deduplicación por lema
    ("CR!BOOK1:4", "en:relied", "She relied on the older maps.", 1_700_000_200_000),
    # sustantivo + preposición: falso positivo de phrasal verb (D-009)
    ("CR!BOOK1:5", "en:stake", "He held a stake in the company.", 1_700_000_300_000),
    # nota al pie pegada al final: caso mayoritario de suciedad
    (
        "CR!BOOK1:6",
        "en:brow",
        "He wiped his brow and said nothing more.[59].[",
        1_700_000_400_000,
    ),
    # frase realmente cortada (0,7 % del corpus)
    (
        "CR!BOOK1:7",
        "en:relied",
        "They relied on nothing but the weather and the",
        1_700_000_250_000,
    ),
    # español: debe quedar fuera con langs=("en",)
    (
        "CR!BOOK2:1",
        "es:salvo",
        "Salvo los internados en un manicomio, nadie protestó.",
        1_700_000_500_000,
    ),
]


def build() -> Path:
    FIXTURE_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(FIXTURE_PATH)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO BOOK_INFO VALUES (?,?,?,?,?,?)", BOOKS)
    con.executemany(
        "INSERT INTO WORDS (id, word, stem, lang, category, timestamp, profileid)"
        " VALUES (?,?,?,?,0,?,'')",
        WORDS,
    )
    con.executemany(
        "INSERT INTO LOOKUPS (id, word_key, book_key, dict_key, pos, usage, timestamp)"
        " VALUES (?,?,?,'dict','POS:1',?,?)",
        [(lid, wk, lid.split(":")[0], usage, ts) for lid, wk, usage, ts in LOOKUPS],
    )
    con.commit()
    con.close()
    return FIXTURE_PATH


if __name__ == "__main__":
    print(f"Fixture creado en {build()}")
