"""Entidades del dominio: vocabulario, contextos y ejercicios, sin dependencias
externas."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Context:
    """La frase de un libro donde apareció una palabra."""

    external_id: str
    raw_sentence: str
    clean_sentence: str
    is_truncated: bool
    captured_at: datetime
    book_title: str | None = None
    book_lang: str | None = None

    @property
    def is_usable(self) -> bool:
        """Si la frase limpia sirve para construir un ejercicio anclado."""
        return bool(self.clean_sentence) and not self.is_truncated


@dataclass
class Entry:
    """Una palabra del vocabulario, con todos sus contextos.

    La identidad es (lemma, lang). Una palabra consultada en varios
    libros es una sola entrada con varios contextos.
    """

    term: str
    lemma: str
    lang: str
    pos: str | None = None
    external_id: str | None = None
    contexts: list[Context] = field(default_factory=list)

    @property
    def identity(self) -> tuple[str, str]:
        return (self.lemma, self.lang)

    @property
    def first_seen_at(self) -> datetime:
        """La consulta más antigua. Nunca WORDS.timestamp (§5.1 del esquema)."""
        return min(c.captured_at for c in self.contexts)

    @property
    def usable_contexts(self) -> list[Context]:
        return [c for c in self.contexts if c.is_usable]
