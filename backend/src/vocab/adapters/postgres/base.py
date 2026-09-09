"""Metadatos y clase base de SQLAlchemy para el adaptador de PostgreSQL."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Nombres deterministas para índices y restricciones.
# Sin esto, PostgreSQL los nombra por su cuenta y Alembic no sabe cómo
# se llaman al generar una migración que los elimine o modifique.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
