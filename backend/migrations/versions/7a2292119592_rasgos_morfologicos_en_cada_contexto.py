"""rasgos morfologicos en cada contexto

Revision ID: 7a2292119592
Revises: fee3d3fffef4
Create Date: 2026-09-25 10:12:36.271944

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a2292119592"
down_revision: str | Sequence[str] | None = "fee3d3fffef4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # contexts.morph solo se puede calcular con spaCy, y una migración no debe
    # depender de un modelo de lenguaje. Tampoco vale dejar NULL en las filas
    # existentes: NULL ya significa «token no localizado» (D-016), y mezclaría
    # los dos casos. Mismo criterio que fee3d3fffef4: con filas, no se ejecuta.
    existing = op.get_bind().scalar(sa.text("SELECT count(*) FROM contexts"))
    if existing:
        raise RuntimeError(
            f"contexts tiene {existing} filas y contexts.morph no se puede "
            "calcular desde la base. Vacíala con `alembic downgrade base`, "
            "vuelve a `alembic upgrade head` y reimporta el vocab.db."
        )
    op.add_column("contexts", sa.Column("morph", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("contexts", "morph")
