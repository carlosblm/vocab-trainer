"""Ejercicio `mcq_definition`: la frase del libro y cuatro definiciones de la
palabra consultada, una correcta (§2.3).

Como `ClozeOriginalChoice` (D-022), el orden de las opciones depende del azar,
así que se fija al crear el ejercicio y se guarda; la corrección es por índice.
No sabe de dónde salen los distractores, si de un modelo (A1) o de la plantilla
determinista (§7.3): eso lo registrará la persistencia.

**El estilo de las opciones se iguala solo al mostrarlas.** Las glosas de
WordNet van en minúscula y sin punto final, y las del modelo pueden llegar con
mayúscula y punto: si cada opción conservara el suyo, la forma delataría la
respuesta. Es la idea del patrón de mayúsculas de D-022. El texto original se
guarda tal cual, y las comparaciones de las invariantes son por palabras y sin
mayúsculas, con la misma normalización que los validadores (D-027).
"""

import random
from dataclasses import dataclass
from typing import Self

from vocab.domain.distractor_validation import word_tokens

# La correcta y tres distractores, como en la variante de elección de
# `cloze_original`: con menos, acertar al azar deja de ser un 25 %.
OPTION_COUNT = 4

# Un signo de estos al final ya cierra la frase, y no se añade punto.
FINAL_PUNCTUATION = (".", "!", "?", "…")


@dataclass(frozen=True)
class McqDefinition:
    """La frase, la forma consultada en ella, la definición correcta y las
    cuatro opciones en el orden en que se muestran.

    - `sentence` es la frase limpia del contexto, y `word`, la forma que se
      consultó en ella (`Context.term`, D-020).
    - `options` incluye la definición correcta y los tres distractores, con
      su texto original.
    """

    sentence: str
    word: str
    definition: str
    options: tuple[str, ...]

    def __post_init__(self) -> None:
        # Invariantes, no decisiones al nacer, como en `ClozeOriginalChoice`:
        # se comprueban también al reconstruir el ejercicio desde la base.
        if len(self.options) != OPTION_COUNT:
            raise ValueError(
                f"hacen falta {OPTION_COUNT} opciones, no {len(self.options)}"
            )
        normalized = [word_tokens(option) for option in self.options]
        if not all(normalized):
            raise ValueError("hay opciones sin ninguna palabra")
        if len(set(normalized)) != OPTION_COUNT:
            raise ValueError("hay opciones repetidas")
        if word_tokens(self.definition) not in normalized:
            raise ValueError("la definición correcta no está entre las opciones")

    @classmethod
    def new(
        cls,
        sentence: str,
        word: str,
        definition: str,
        distractors: tuple[str, str, str],
        rng: random.Random,
    ) -> Self:
        """El ejercicio con las cuatro opciones en un orden al azar. `rng`
        entra por parámetro para que un test con semilla sea reproducible."""
        options = [definition, *distractors]
        rng.shuffle(options)
        return cls(
            sentence=sentence, word=word, definition=definition, options=tuple(options)
        )

    @property
    def answer_index(self) -> int:
        """La posición de la definición correcta entre las opciones.

        Única: las invariantes garantizan que las cuatro son distintas por
        palabras y que la correcta está entre ellas.
        """
        target = word_tokens(self.definition)
        return next(
            index
            for index, option in enumerate(self.options)
            if word_tokens(option) == target
        )

    @property
    def distractors(self) -> tuple[str, ...]:
        """Las tres opciones que no son la correcta, en su orden."""
        answer = self.answer_index
        return tuple(
            option for index, option in enumerate(self.options) if index != answer
        )

    @property
    def displayed_options(self) -> tuple[str, ...]:
        """Las cuatro opciones con el mismo estilo, para mostrarlas."""
        return tuple(displayed(option) for option in self.options)

    def is_correct(self, index: int) -> bool:
        """Si la opción elegida, por su posición desde 0, es la correcta."""
        return index == self.answer_index


def displayed(text: str) -> str:
    """El texto como se muestra: sin espacios sobrantes, con la primera letra
    en mayúscula y con punto final si no acaba ya en un signo que cierre.

    Solo cambia esa letra: el resto se deja tal cual, así que una sigla
    (`DNA`, `U.S.`) no se toca. La primera letra puede ir detrás de un
    paréntesis, como en las glosas de WordNet que empiezan por su ámbito:
    «(law) a party…» se muestra «(Law) a party…».
    """
    collapsed = " ".join(text.split())
    for index, character in enumerate(collapsed):
        if character.isalpha():
            collapsed = collapsed[:index] + character.upper() + collapsed[index + 1 :]
            break
    if collapsed and not collapsed.endswith(FINAL_PUNCTUATION):
        collapsed += "."
    return collapsed
