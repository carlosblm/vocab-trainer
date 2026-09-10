"""Fábrica de sesiones de SQLAlchemy."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from vocab.config import get_settings

_engine = create_engine(get_settings().database_url, future=True)
_SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Sesión transaccional: confirma al salir, revierte si hay error."""
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
