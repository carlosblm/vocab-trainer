"""Puertos de persistencia: un contrato por caso de uso (D-023).

Importar y estudiar no comparten casi nada, salvo saber quién es el usuario.
Con un solo contrato, cada doble de prueba tenía que implementar métodos que
su caso de uso nunca llama, y el problema crecía con cada método nuevo.

La separación no le cuesta nada al adaptador: un `Protocol` se cumple por
forma, no por herencia, así que el mismo adaptador de Postgres satisface los
dos sin declararlo. Lo comprueba mypy en la raíz de composición, al pasarlo a
cada caso de uso.
"""

from dataclasses import dataclass
from typing import Protocol

from vocab.domain.models import Entry


@dataclass(frozen=True)
class ImportStats:
    entries_created: int
    entries_existing: int
    contexts_created: int
    contexts_existing: int


class ImportRepository(Protocol):
    """Lo que necesita la importación: persistir entradas y contextos de forma
    idempotente."""

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
    ) -> ImportStats:
        """Inserta lo que no existe. Nunca modifica ni borra lo existente."""
        ...


class StudyRepository(Protocol):
    """Lo que necesita el estudio: leer las entradas que se pueden estudiar."""

    def ensure_user(self) -> int:
        """Devuelve el id del usuario único de la v1, creándolo si no existe."""
        ...

    def list_learning_entries_with_usable_context(self, user_id: int) -> list[Entry]:
        """Entradas en estudio (`learning`) con al menos un contexto utilizable.

        Cada entrada llega completa, con todos sus contextos: elegir entre los
        utilizables es cosa de quien llama (`Entry.usable_contexts`). El orden
        es estable entre llamadas, para que una elección al azar con semilla
        sea reproducible.
        """
        ...

    def list_non_noise_entries(self, user_id: int) -> list[Entry]:
        """Todas las entradas salvo las `noise`, `known` incluidas: de ellas
        salen los distractores de la variante de elección (D-022).

        Cada entrada llega completa, con todos sus contextos, también los
        truncados o sin analizar: decidir cuáles sirven es cosa de la regla de
        distractores. El orden es estable, por la misma razón que arriba.
        """
        ...
