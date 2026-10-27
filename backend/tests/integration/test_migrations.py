"""Las migraciones con algo que comprobar:

- `b6f0529d57e8` se niega a ejecutarse si `contexts` tiene filas, y sin filas
  añade las columnas (D-033, con el criterio de D-020 y D-022).
- `8448e3e315a1` crea `exercises` y `definition_flags`, y las borra al bajar.

Ejecuta Alembic de verdad sobre una base aparte del mismo Postgres de
testcontainers: la de los demás tests se crea con `create_all`, sin Alembic.
`env.py` lee la URL de `DATABASE_URL`, como en producción.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text

from vocab.adapters.postgres.base import Base
from vocab.adapters.postgres.tables import DefinitionFlagRow, ExerciseRow
from vocab.config import get_settings

MIGRATIONS = Path(__file__).parents[2] / "migrations"
PREVIOUS = "7a2292119592"
REVISION = "b6f0529d57e8"
NEW_COLUMNS = {"particle", "definition_status", "definition", "sense_id", "lexicon"}
EXERCISES_REVISION = "8448e3e315a1"
# De las clases y no escritos: importarlas registra todas las tablas en
# `Base.metadata`, con el que se compara el esquema.
EXERCISE_TABLES = {ExerciseRow.__tablename__, DefinitionFlagRow.__tablename__}
DATABASE = "migration_check"


@pytest.fixture
def empty_database(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Una base vacía en el servidor de testcontainers, con `DATABASE_URL`
    apuntando a ella. Se borra al terminar."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f"DROP DATABASE IF EXISTS {DATABASE}"))
        admin.execute(text(f"CREATE DATABASE {DATABASE}"))
    url = engine.url.set(database=DATABASE)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    database = create_engine(url)
    yield database
    database.dispose()
    get_settings.cache_clear()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f"DROP DATABASE {DATABASE}"))


def _alembic() -> Config:
    """Sin `alembic.ini`, para que `env.py` no reconfigure el logging del
    proceso de los tests; solo hace falta dónde están las migraciones."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def _revision(database: Engine) -> str:
    with database.connect() as connection:
        revision: str = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    return revision


def _columns(database: Engine) -> set[str]:
    return {column["name"] for column in inspect(database).get_columns("contexts")}


def test_migration_refuses_to_run_over_existing_contexts(
    empty_database: Engine,
) -> None:
    """Con una fila, aborta y explica qué hacer. La base se queda en la
    revisión anterior, porque el DDL de Postgres es transaccional."""
    command.upgrade(_alembic(), PREVIOUS)
    with empty_database.begin() as connection:
        user_id = connection.execute(
            text("INSERT INTO users DEFAULT VALUES RETURNING id")
        ).scalar_one()
        entry_id = connection.execute(
            text(
                "INSERT INTO entries (user_id, term, lemma, lang, first_seen_at) "
                "VALUES (:user_id, 'craved', 'crave', 'en', now()) RETURNING id"
            ),
            {"user_id": user_id},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO contexts (entry_id, term, raw_sentence, is_truncated, "
                "captured_at) VALUES (:entry_id, 'craved', 'She craved it.', false, "
                "now())"
            ),
            {"entry_id": entry_id},
        )

    with pytest.raises(RuntimeError, match="downgrade base.*upgrade head.*reimporta"):
        command.upgrade(_alembic(), "head")

    assert _revision(empty_database) == PREVIOUS
    assert not NEW_COLUMNS & _columns(empty_database)


def test_migration_adds_the_columns_over_an_empty_table(
    empty_database: Engine,
) -> None:
    command.upgrade(_alembic(), REVISION)

    assert _revision(empty_database) == REVISION
    assert NEW_COLUMNS <= _columns(empty_database)

    command.downgrade(_alembic(), PREVIOUS)

    assert not NEW_COLUMNS & _columns(empty_database)


def test_exercises_migration_creates_both_tables_and_drops_them(
    empty_database: Engine,
) -> None:
    """Sube hasta la última y deja el mismo esquema que las tablas de
    SQLAlchemy, con las que se crean las bases de los demás tests: si no, esos
    tests probarían otra cosa que la base real."""
    command.upgrade(_alembic(), "head")

    assert _revision(empty_database) == EXERCISES_REVISION
    assert EXERCISE_TABLES <= set(inspect(empty_database).get_table_names())
    with empty_database.connect() as connection:
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )

    command.downgrade(_alembic(), REVISION)

    assert _revision(empty_database) == REVISION
    assert not EXERCISE_TABLES & set(inspect(empty_database).get_table_names())
