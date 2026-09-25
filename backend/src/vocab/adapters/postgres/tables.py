"""Definición de las tablas de PostgreSQL.

Estas clases son la representación de persistencia, NO el modelo de dominio.
El dominio va en `vocab.domain.models` sin SQLAlchemy.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from vocab.adapters.postgres.base import Base


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceRow(Base):
    """Un archivo importado. `checksum` hace la importación idempotente."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("user_id", "checksum"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EntryRow(Base):
    """Una palabra del vocabulario, deduplicada por (usuario, lema, idioma)."""

    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("user_id", "lemma", "lang"),
        CheckConstraint(
            "status IN ('learning', 'known', 'noise')", name="status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    term: Mapped[str] = mapped_column(String(120))
    lemma: Mapped[str] = mapped_column(String(120))
    lang: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="learning")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContextRow(Base):
    """La frase del libro. `raw_sentence` nunca se modifica.

    `term` es la forma consultada en esta frase; `entries.term` es solo la de
    la consulta más antigua de la entrada.
    """

    __tablename__ = "contexts"
    __table_args__ = (UniqueConstraint("entry_id", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entries.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    term: Mapped[str] = mapped_column(String(120))
    raw_sentence: Mapped[str] = mapped_column(Text)
    clean_sentence: Mapped[str | None] = mapped_column(Text)
    is_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    pos: Mapped[str | None] = mapped_column(String(16))
    morph: Mapped[str | None] = mapped_column(String(255))
    book_title: Mapped[str | None] = mapped_column(String(500))
    book_lang: Mapped[str | None] = mapped_column(String(8))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
