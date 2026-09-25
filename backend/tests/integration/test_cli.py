"""La CLI de extremo a extremo contra el Postgres de testcontainers.

Prueba lo que solo existe en la raíz de composición: que la configuración llega
por `DATABASE_URL`, que los adaptadores quedan cableados y que la transacción
se confirma donde debe. Las reglas del ejercicio y la elección al azar tienen
sus propios tests unitarios.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from vocab.adapters.postgres.base import Base
from vocab.adapters.postgres.tables import ContextRow, EntryRow, UserRow
from vocab.cli.main import app
from vocab.config import get_settings
from vocab.domain.exercises.cloze_original import BLANK

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"

runner = CliRunner()


@pytest.fixture
def database(engine, monkeypatch):
    """La CLI lee `DATABASE_URL` como en producción; aquí apunta al contenedor.

    `get_settings` está cacheada, así que se vacía antes y después. La CLI
    confirma con sus propias sesiones, así que las tablas se vacían a mano.
    """
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    yield engine
    get_settings.cache_clear()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


def _count(engine, table) -> int:
    """Cuenta desde una sesión nueva: solo ve lo que alguien confirmó."""
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(table))


def _only_in_study(engine, lemma: str) -> None:
    """Deja una sola entrada `learning`, para que el azar no tenga dónde
    elegir."""
    with engine.begin() as connection:
        connection.execute(
            update(EntryRow).where(EntryRow.lemma != lemma).values(status="known")
        )


def test_import_commits_what_it_imports(database):
    result = runner.invoke(app, ["import", str(FIXTURE)])

    assert result.exit_code == 0, result.output
    assert "Entradas: 5 nuevas, 0 ya existían." in result.output
    assert "Contextos: 8 nuevos, 0 ya existían." in result.output
    assert _count(database, EntryRow) == 5
    assert _count(database, ContextRow) == 8


def test_import_of_a_missing_file_fails_before_touching_the_database(
    database, tmp_path
):
    result = runner.invoke(app, ["import", str(tmp_path / "vocab.db")])

    assert result.exit_code == 2
    assert "does not exist" in result.output
    assert _count(database, UserRow) == 0


def test_study_with_nothing_to_study_says_so_and_writes_nothing(database):
    """`ensure_user` crea el usuario en una base vacía; `study` nunca
    confirma, así que no queda escrito."""
    result = runner.invoke(app, ["study"])

    assert result.exit_code == 0, result.output
    assert "No hay entradas en estudio" in result.output
    assert _count(database, UserRow) == 0


def test_study_accepts_the_answer_ignoring_case_and_spaces(database):
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "stake")

    result = runner.invoke(app, ["study"], input="  STAKE \n")

    assert result.exit_code == 0, result.output
    assert f"He held a {BLANK} in the company." in result.output
    assert "Correcto." in result.output
    assert "1 de 1 correctas." in result.output


def test_study_shows_the_word_and_the_clean_sentence_after_a_miss(database):
    """El contexto de `brow` llega sucio (`…more.[59].[`): tras el fallo se
    muestra la frase limpia, no la cruda."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "brow")

    result = runner.invoke(app, ["study"], input="brows\n")

    assert result.exit_code == 0, result.output
    assert "Incorrecto. La palabra era «brow»." in result.output
    assert "Frase: He wiped his brow and said nothing more." in result.output
    assert "[59]" not in result.output
    assert "0 de 1 correctas." in result.output
