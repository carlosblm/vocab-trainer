"""La CLI de extremo a extremo contra el Postgres de testcontainers.

Prueba lo que solo existe en la raíz de composición: que la configuración llega
por `DATABASE_URL`, que los adaptadores quedan cableados y que la transacción
se confirma donde debe. Las reglas del ejercicio y la elección al azar tienen
sus propios tests unitarios.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from vocab.adapters.postgres.base import Base
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import ContextRow, EntryRow, UserRow
from vocab.cli.main import app
from vocab.config import get_settings
from vocab.domain.exercises.cloze_original import BLANK
from vocab.domain.models import Context, Entry, EntryStatus

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


def _count(engine: Engine, table: type[Base]) -> int:
    """Cuenta desde una sesión nueva: solo ve lo que alguien confirmó."""
    with Session(engine) as session:
        return session.execute(select(func.count()).select_from(table)).scalar_one()


def _only_in_study(engine: Engine, lemma: str) -> None:
    """Deja una sola entrada `learning`, para que el azar no tenga dónde
    elegir."""
    with engine.begin() as connection:
        connection.execute(
            update(EntryRow).where(EntryRow.lemma != lemma).values(status="known")
        )


def _add_known_past_verbs(engine: Engine, *terms: str) -> None:
    """Entradas `known` en pasado: con `relied` del fixture, dan a `eased` los
    tres distractores de la variante de elección."""
    with Session(engine) as session:
        repository = PostgresVocabularyRepository(session)
        user_id = repository.ensure_user()
        source_id = repository.register_source(user_id, "test", "test", "extra")
        entries = [
            Entry(
                term=term,
                lemma=term,
                lang="en",
                status=EntryStatus.KNOWN,
                contexts=[
                    Context(
                        external_id=f"extra:{term}",
                        term=term,
                        raw_sentence=f"They {term} it.",
                        clean_sentence=f"They {term} it.",
                        is_truncated=False,
                        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
                        pos="VERB",
                        morph="Tense=Past|VerbForm=Fin",
                    )
                ],
            )
            for term in terms
        ]
        repository.upsert_entries(user_id, source_id, entries)
        session.commit()


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

    result = runner.invoke(app, ["study", "--write"], input="  STAKE \n")

    assert result.exit_code == 0, result.output
    assert f"He held a {BLANK} in the company." in result.output
    assert "Correcto." in result.output
    assert "1 de 1 correctas." in result.output


def test_study_shows_the_word_and_the_clean_sentence_after_a_miss(database):
    """El contexto de `brow` llega sucio (`…more.[59].[`): tras el fallo se
    muestra la frase limpia, no la cruda."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "brow")

    result = runner.invoke(app, ["study", "--write"], input="brows\n")

    assert result.exit_code == 0, result.output
    assert "Incorrecto. La palabra era «brow»." in result.output
    assert "Frase: He wiped his brow and said nothing more." in result.output
    assert "[59]" not in result.output
    assert "0 de 1 correctas." in result.output


def test_study_offers_four_options_and_takes_a_number_or_the_word(database):
    """El orden de las opciones es aleatorio: el test lee cuál es la 1 y
    comprueba que el veredicto le corresponde."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "ease")
    _add_known_past_verbs(database, "tossed", "waned")

    result = runner.invoke(app, ["study"], input="1\neased\n")

    assert result.exit_code == 0, result.output
    assert "Sin opciones" not in result.output
    first_exercise = result.output.split("Elige (1-4)")[0]
    options = dict(re.findall(r"^  (\d)\) (\S+)$", first_exercise, re.MULTILINE))
    assert sorted(options.values()) == ["eased", "relied", "tossed", "waned"]
    verdicts = re.findall(r"^(Correcto|Incorrecto)", result.output, re.MULTILINE)
    first_verdict = "Correcto" if options["1"] == "eased" else "Incorrecto"
    assert verdicts == [first_verdict, "Correcto"]


def test_study_without_three_distractors_asks_to_write_and_says_why(database):
    """`stake` solo comparte forma con `brow`: el aviso dice cuántas hay, cuál
    es la forma y por qué hacen falta tres."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "stake")

    result = runner.invoke(app, ["study"], input="stake\n")

    assert result.exit_code == 0, result.output
    assert (
        "Sin opciones: solo otra de tus palabras consultadas tiene su misma forma "
        "gramatical (NOUN Number=Sing), y hacen falta 3 para que la gramática no "
        "delate la respuesta. Escríbela."
    ) in result.output
    assert "Elige" not in result.output
    assert "Correcto." in result.output


def test_study_write_asks_to_type_even_when_there_are_options(database):
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "ease")
    _add_known_past_verbs(database, "tossed", "waned")

    result = runner.invoke(app, ["study", "--write"], input="eased\n")

    assert result.exit_code == 0, result.output
    assert f"Electronics {BLANK} out hydraulics in the new design." in result.output
    assert ") eased" not in result.output
    assert "Sin opciones" not in result.output
    assert "Correcto." in result.output
