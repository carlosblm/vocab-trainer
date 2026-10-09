import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from vocab.adapters.lexicon import LexiconNotDownloaded, OewnLexicon
from vocab.adapters.postgres.base import Base
from vocab.config import get_settings


@pytest.fixture(scope="session")
def engine():
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        engine = create_engine(container.get_connection_url())
        Base.metadata.create_all(engine)
        yield engine


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(scope="session")
def lexicon() -> OewnLexicon:
    """El léxico real de D-025. Los tests que lo piden se saltan si
    `WN_DATA_DIR` no está definido o el léxico no está descargado."""
    data_dir = get_settings().wn_data_dir
    if data_dir is None:
        pytest.skip("requiere WN_DATA_DIR con el léxico oewn:2025 descargado")
    try:
        return OewnLexicon(data_dir)
    except LexiconNotDownloaded as error:
        pytest.skip(str(error))
