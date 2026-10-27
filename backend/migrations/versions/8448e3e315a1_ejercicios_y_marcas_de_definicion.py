"""ejercicios y marcas de definicion

Revision ID: 8448e3e315a1
Revises: b6f0529d57e8
Create Date: 2026-10-26 19:48:31.116456

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8448e3e315a1"
down_revision: str | Sequence[str] | None = "b6f0529d57e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Dos tablas nuevas y nada que calcular para las filas existentes: al
    # revés que b6f0529d57e8, se ejecuta también con datos.
    #
    # VARCHAR + CHECK, no ENUM de Postgres, como entries.status: un valor nuevo
    # no debe requerir ALTER TYPE.
    op.create_table(
        "exercises",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("context_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("distractor_source", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("attempts", postgresql.JSONB(), nullable=False),
        sa.Column("degradation_cause", sa.String(length=32), nullable=True),
        sa.Column("degradation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('cloze_original', 'mcq_definition')",
            name=op.f("ck_exercises_kind_valid"),
        ),
        sa.CheckConstraint(
            "distractor_source IN ('model', 'template', 'none')",
            name=op.f("ck_exercises_distractor_source_valid"),
        ),
        sa.CheckConstraint(
            "degradation_cause IN ('provider_unavailable', 'retries_exhausted', "
            "'no_generator', 'exercise_rejected')",
            name=op.f("ck_exercises_degradation_cause_valid"),
        ),
        sa.CheckConstraint(
            "(kind = 'mcq_definition') = (distractor_source <> 'none')",
            name=op.f("ck_exercises_source_matches_kind"),
        ),
        sa.CheckConstraint(
            "(model IS NULL) = (prompt_version IS NULL)",
            name=op.f("ck_exercises_generator_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["contexts.id"],
            name=op.f("fk_exercises_context_id_contexts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name=op.f("fk_exercises_entry_id_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercises")),
    )
    op.create_index(
        op.f("ix_exercises_context_id"), "exercises", ["context_id"], unique=False
    )
    op.create_index(
        op.f("ix_exercises_entry_id"), "exercises", ["entry_id"], unique=False
    )
    op.create_table(
        "definition_flags",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("context_id", sa.BigInteger(), nullable=False),
        sa.Column("sense_id", sa.String(length=255), nullable=False),
        sa.Column("lexicon", sa.String(length=64), nullable=False),
        sa.Column(
            "flagged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["contexts.id"],
            name=op.f("fk_definition_flags_context_id_contexts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_definition_flags")),
        sa.UniqueConstraint(
            "context_id",
            "sense_id",
            "lexicon",
            name=op.f("uq_definition_flags_context_id"),
        ),
    )
    op.create_index(
        op.f("ix_definition_flags_context_id"),
        "definition_flags",
        ["context_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Borra los ejercicios guardados y las marcas del usuario: no hay otra
    # forma de deshacer dos tablas nuevas.
    op.drop_index(op.f("ix_definition_flags_context_id"), table_name="definition_flags")
    op.drop_table("definition_flags")
    op.drop_index(op.f("ix_exercises_entry_id"), table_name="exercises")
    op.drop_index(op.f("ix_exercises_context_id"), table_name="exercises")
    op.drop_table("exercises")
