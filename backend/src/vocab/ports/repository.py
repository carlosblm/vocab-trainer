"""Puerto de persistencia: interfaz de acceso a la base de datos de vocabulario."""

from dataclasses import dataclass
from typing import Protocol

from vocab.domain.models import Entry


@dataclass(frozen=True)
class ImportStats:
    entries_created: int
    entries_existing: int
    contexts_created: int
    contexts_existing: int


class VocabularyRepository(Protocol):
    """Persiste entradas y contextos de forma idempotente."""

    def ensure_user(self) -> int:
        """Devuelve el id del usuario único de la v1, creándolo si no existe."""
        ...

    def register_source(
        self, user_id: int, kind: str, filename: str, checksum: str
    ) -> int:
        """Registra el archivo importado y devuelve su id."""
        ...

    def upsert_entries(
        self, user_id: int, source_id: int, entries: list[Entry]
    ) -> "ImportStats":
        """Inserta lo que no existe. Nunca modifica ni borra lo existente."""
        ...
