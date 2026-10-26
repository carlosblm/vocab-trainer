"""particula y definicion de cada contexto

Revision ID: b6f0529d57e8
Revises: 7a2292119592
Create Date: 2026-10-09 16:19:39.559264

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6f0529d57e8"
down_revision: str | Sequence[str] | None = "7a2292119592"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # La partícula sale de spaCy y la definición, del léxico: ninguna se puede
    # calcular desde la base, y una migración no debe depender de un modelo de
    # lenguaje ni de un léxico. Tampoco vale dejar NULL en las filas
    # existentes: un estado NULL ya significa «no evaluado, porque spaCy no
    # localizó la palabra» (D-016), y mezclaría los dos casos. Mismo criterio
    # que fee3d3fffef4 y 7a2292119592: con filas, no se ejecuta.
    existing = op.get_bind().scalar(sa.text("SELECT count(*) FROM contexts"))
    if existing:
        raise RuntimeError(
            f"contexts tiene {existing} filas, y su partícula y su definición "
            "no se pueden calcular desde la base. Vacíala con `alembic "
            "downgrade base`, vuelve a `alembic upgrade head` y reimporta el "
            "vocab.db."
        )
    op.add_column("contexts", sa.Column("particle", sa.String(length=32)))
    op.add_column("contexts", sa.Column("definition_status", sa.String(length=32)))
    op.add_column("contexts", sa.Column("definition", sa.Text()))
    op.add_column("contexts", sa.Column("sense_id", sa.String(length=255)))
    op.add_column("contexts", sa.Column("lexicon", sa.String(length=64)))
    # VARCHAR + CHECK, no ENUM de Postgres, como entries.status: un estado
    # nuevo no debe requerir ALTER TYPE.
    op.create_check_constraint(
        op.f("ck_contexts_definition_status_valid"),
        "contexts",
        "definition_status IN ('eligible', 'pos_unmapped', 'form_not_found', "
        "'lemma_disagrees', 'lexical_unit', 'polysemous')",
    )
    op.create_check_constraint(
        op.f("ck_contexts_definition_only_if_eligible"),
        "contexts",
        "COALESCE(definition_status = 'eligible', false) = (definition IS NOT NULL)"
        " AND COALESCE(definition_status = 'eligible', false) = "
        "(sense_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_contexts_lexicon_with_status"),
        "contexts",
        "(definition_status IS NULL) = (lexicon IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_contexts_lexicon_with_status"), "contexts")
    op.drop_constraint(op.f("ck_contexts_definition_only_if_eligible"), "contexts")
    op.drop_constraint(op.f("ck_contexts_definition_status_valid"), "contexts")
    op.drop_column("contexts", "lexicon")
    op.drop_column("contexts", "sense_id")
    op.drop_column("contexts", "definition")
    op.drop_column("contexts", "definition_status")
    op.drop_column("contexts", "particle")
