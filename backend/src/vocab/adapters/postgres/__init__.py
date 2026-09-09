"""Adaptador de persistencia sobre PostgreSQL."""

from vocab.adapters.postgres.base import Base
from vocab.adapters.postgres.tables import ContextRow, EntryRow, SourceRow, UserRow

__all__ = ["Base", "ContextRow", "EntryRow", "SourceRow", "UserRow"]
