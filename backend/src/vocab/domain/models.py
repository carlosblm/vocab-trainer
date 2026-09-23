"""Entidades del dominio: vocabulario, contextos y ejercicios, sin dependencias
externas."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Self

from vocab.domain.noise import LookedUpWord, is_noise


class EntryStatus(Enum):
    """Estado de estudio de una entrada, controlado por el usuario (D-014)."""

    LEARNING = "learning"
    KNOWN = "known"
    NOISE = "noise"


@dataclass(frozen=True)
class Context:
    """La frase de un libro donde apareció una palabra."""

    external_id: str
    raw_sentence: str
    clean_sentence: str
    is_truncated: bool
    captured_at: datetime
    pos: str | None = None
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
    external_id: str | None = None
    status: EntryStatus = EntryStatus.LEARNING
    contexts: list[Context] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        word: LookedUpWord,
        lemma: str,
        external_id: str | None,
        contexts: list[Context],
    ) -> Self:
        """Crea una entrada descubierta ahora y decide con qué estado nace.

        Reconstruir una entrada ya guardada no pasa por aquí: usa el
        constructor normal, que acepta cualquier estado. El `known` que puso el
        usuario tiene que sobrevivir a la reimportación (D-014), así que el
        estado solo se calcula la primera vez que se ve la palabra.
        """
        return cls(
            term=word.text,
            lemma=lemma,
            lang=word.lang,
            external_id=external_id,
            status=EntryStatus.NOISE if is_noise(word) else EntryStatus.LEARNING,
            contexts=contexts,
        )

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
