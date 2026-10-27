"""Definición de las tablas de PostgreSQL.

Estas clases son la representación de persistencia, NO el modelo de dominio.
El dominio va en `vocab.domain.models` sin SQLAlchemy.
"""

from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
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

    `particle` es la de la guarda R1, y las cuatro columnas de definición son
    la decisión de la política de D-025 al importar (D-033). Las CHECK
    repiten en la base la invariante de `DefinitionDecision`: `definition` y
    `sense_id` solo con `eligible`, y `lexicon` siempre que haya estado. Un
    estado `NULL` es un contexto sin evaluar, y entonces no hay nada más.
    """

    __tablename__ = "contexts"
    __table_args__ = (
        UniqueConstraint("entry_id", "external_id"),
        CheckConstraint(
            "definition_status IN ('eligible', 'pos_unmapped', 'form_not_found', "
            "'lemma_disagrees', 'lexical_unit', 'polysemous')",
            name="definition_status_valid",
        ),
        CheckConstraint(
            "COALESCE(definition_status = 'eligible', false) = (definition IS NOT NULL)"
            " AND COALESCE(definition_status = 'eligible', false) = "
            "(sense_id IS NOT NULL)",
            name="definition_only_if_eligible",
        ),
        CheckConstraint(
            "(definition_status IS NULL) = (lexicon IS NULL)",
            name="lexicon_with_status",
        ),
    )

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
    particle: Mapped[str | None] = mapped_column(String(32))
    definition_status: Mapped[str | None] = mapped_column(String(32))
    definition: Mapped[str | None] = mapped_column(Text)
    sense_id: Mapped[str | None] = mapped_column(String(255))
    lexicon: Mapped[str | None] = mapped_column(String(64))
    book_title: Mapped[str | None] = mapped_column(String(500))
    book_lang: Mapped[str | None] = mapped_column(String(8))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExerciseRow(Base):
    """Un ejercicio mostrado. Se escribe al mostrarlo y no se modifica.

    - `payload` es lo necesario para reconstruirlo: la frase, la palabra, la
      respuesta (`definition` en `mcq_definition`) y las opciones en su orden,
      `null` en la variante de escritura. JSONB y no columnas: cada tipo de
      ejercicio tiene las suyas, y F3 añadirá más tipos.
    - `distractor_source`, `model`, `prompt_version`, `attempts` y
      `degradation_cause` son la procedencia de los distractores. `model` y
      `prompt_version` son los del generador si se le pidió algo, aunque
      degradara (D-007).
    - `entry_id` repite lo que dice `context_id`: es la entrada la que tendrá
      repasos y estado de repaso en F3 (§4.3).

    Los valores de `kind`, `distractor_source`, `degradation_cause` y del
    historial se escriben a mano en `ports.exercise_record`. Las CHECK repiten
    los conjuntos de valores y las dos invariantes que se pueden decir en una
    línea; el resto lo comprueba `ExerciseRecord` al leer.
    """

    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('cloze_original', 'mcq_definition')", name="kind_valid"
        ),
        CheckConstraint(
            "distractor_source IN ('model', 'template', 'none')",
            name="distractor_source_valid",
        ),
        CheckConstraint(
            "degradation_cause IN ('provider_unavailable', 'retries_exhausted', "
            "'no_generator', 'exercise_rejected')",
            name="degradation_cause_valid",
        ),
        CheckConstraint(
            "(kind = 'mcq_definition') = (distractor_source <> 'none')",
            name="source_matches_kind",
        ),
        CheckConstraint(
            "(model IS NULL) = (prompt_version IS NULL)", name="generator_complete"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entries.id", ondelete="CASCADE"), index=True
    )
    context_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contexts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    lang: Mapped[str] = mapped_column(String(8))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    distractor_source: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    degradation_cause: Mapped[str | None] = mapped_column(String(32))
    degradation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DefinitionFlagRow(Base):
    """La marca «la definición no encaja»: un contexto y el sentido que se
    marcó, con la fecha. Es dato del usuario, como el progreso: la importación
    no escribe aquí (D-012). Una por contexto y sentido: marcar dos veces no
    añade nada."""

    __tablename__ = "definition_flags"
    __table_args__ = (UniqueConstraint("context_id", "sense_id", "lexicon"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    context_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contexts.id", ondelete="CASCADE"), index=True
    )
    sense_id: Mapped[str] = mapped_column(String(255))
    lexicon: Mapped[str] = mapped_column(String(64))
    flagged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
