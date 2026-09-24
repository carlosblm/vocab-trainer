"""forma consultada en cada contexto

Revision ID: fee3d3fffef4
Revises: 3cd85c3c0ec2
Create Date: 2026-09-24 18:46:09.336513

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fee3d3fffef4"
down_revision: str | Sequence[str] | None = "3cd85c3c0ec2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # contexts.term no se puede reconstruir desde la base: es la palabra que
    # tocó el lector, y solo está en la fuente. Rellenarla con entries.term
    # pondría una forma falsa en 58 de los 1.024 contextos de la exportación de
    # septiembre de 2026, y lo haría en silencio. Así que la migración no
    # inventa nada: se niega a correr sobre una tabla con filas. Hasta F3 no
    # hay progreso que perder, así que vaciar y reimportar es lo correcto.
    existing = op.get_bind().scalar(sa.text("SELECT count(*) FROM contexts"))
    if existing:
        raise RuntimeError(
            f"contexts tiene {existing} filas y contexts.term no se puede "
            "reconstruir desde la base. Vacíala con `alembic downgrade base`, "
            "vuelve a `alembic upgrade head` y reimporta el vocab.db."
        )
    op.add_column("contexts", sa.Column("term", sa.String(length=120), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("contexts", "term")
