from datetime import UTC, datetime
from pathlib import Path

import pytest

from vocab.adapters.kindle import KindleVocabImporter

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"


@pytest.fixture
def importer() -> KindleVocabImporter:
    return KindleVocabImporter(FIXTURE)


def test_kind_es_kindle(importer):
    assert importer.kind == "kindle"


def test_checksum_es_estable(importer):
    assert importer.checksum() == importer.checksum()
    assert len(importer.checksum()) == 64


def test_filtra_por_idioma(importer):
    langs = {lk.lang for lk in importer.read()}
    assert langs == {"en"}


def test_incluye_espanol_si_se_pide():
    todos = KindleVocabImporter(FIXTURE, langs=("en", "es"))
    assert {lk.lang for lk in todos.read()} == {"en", "es"}


def test_una_palabra_puede_tener_varios_contextos(importer):
    resilient = [lk for lk in importer.read() if lk.word == "resilient"]
    assert len(resilient) == 2
    assert len({lk.external_id for lk in resilient}) == 2


def test_no_normaliza_nada(importer):
    """El importador entrega la frase cruda: espacios y notas al pie incluidos."""
    frases = {lk.external_id: lk.sentence for lk in importer.read()}
    assert frases["CR!BOOK1:1"].startswith(" ")
    assert frases["CR!BOOK1:6"].endswith("[")


def test_timestamp_en_utc(importer):
    lk = next(iter(importer.read()))
    assert lk.looked_up_at.tzinfo is not None
    assert lk.looked_up_at == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_no_modifica_el_archivo(importer):
    antes = FIXTURE.stat().st_mtime_ns
    list(importer.read())
    assert FIXTURE.stat().st_mtime_ns == antes
