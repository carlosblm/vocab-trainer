"""estado de entrada y mueve pos de entries a contexts

Revision ID: 3cd85c3c0ec2
Revises: c502a77d28b2
Create Date: 2026-09-18 12:07:01.373753

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3cd85c3c0ec2"
down_revision: str | Sequence[str] | None = "c502a77d28b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # (a) entries.status — VARCHAR + CHECK, no ENUM de Postgres: añadir un
    # valor nuevo no debe requerir ALTER TYPE. server_default porque la
    # tabla ya tiene filas.
    op.add_column(
        "entries",
        sa.Column(
            "status", sa.String(length=16), server_default="learning", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_entries_status_valid"),
        "entries",
        "status IN ('learning', 'known', 'noise')",
    )

    # (b) pos se mueve de entries a contexts: autogenerate lo ve como
    # drop + add y destruiría el dato existente. Se añade la columna nueva,
    # se copia el valor de cada entrada a todos sus contextos y solo
    # entonces se elimina la columna vieja.
    op.add_column("contexts", sa.Column("pos", sa.String(length=16), nullable=True))
    op.execute(
        """
        UPDATE contexts
        SET pos = entries.pos
        FROM entries
        WHERE contexts.entry_id = entries.id
          AND entries.pos IS NOT NULL
        """
    )
    op.drop_column("entries", "pos")


def downgrade() -> None:
    """Downgrade schema."""
    # (b) pos vuelve a entries. Una entrada puede tener contextos con `pos`
    # distinto (la categoría gramatical depende de la frase); se toma el del
    # contexto más reciente como representativo, a sabiendas de que es una
    # pérdida de información respecto al estado por contexto.
    op.add_column(
        "entries", sa.Column("pos", sa.String(length=16), nullable=True)
    )
    op.execute(
        """
        UPDATE entries
        SET pos = latest.pos
        FROM (
            SELECT DISTINCT ON (entry_id) entry_id, pos
            FROM contexts
            WHERE pos IS NOT NULL
            ORDER BY entry_id, captured_at DESC
        ) AS latest
        WHERE entries.id = latest.entry_id
        """
    )
    op.drop_column("contexts", "pos")

    # (a) entries.status desaparece.
    op.drop_constraint(op.f("ck_entries_status_valid"), "entries", type_="check")
    op.drop_column("entries", "status")
