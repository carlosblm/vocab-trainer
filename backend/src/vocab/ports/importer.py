"""Puerto de importación: interfaz que toda fuente de vocabulario debe implementar."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawLookup:
    """Una consulta tal como viene de la fuente, sin normalizar.

    Objeto de transferencia entre el adaptador de importación y la
    normalización. No es una entidad de dominio (no tiene lema ni
    categoría gramatical, porque esos datos no existen en el origen).
    """

    external_id: str
    word: str
    lang: str
    sentence: str
    looked_up_at: datetime
    source_hint: str | None = None
    book_title: str | None = None
    book_lang: str | None = None


class VocabularyImporter(Protocol):
    """Toda fuente de vocabulario implementa esto y nada más."""

    @property
    def kind(self) -> str:
        """Identificador de la fuente: 'kindle', 'csv', 'anki'."""
        ...

    def checksum(self) -> str:
        """Huella del archivo, para registrar qué se importó."""
        ...

    def read(self) -> Iterator[RawLookup]:
        """Emite las consultas del archivo, una a una."""
        ...
