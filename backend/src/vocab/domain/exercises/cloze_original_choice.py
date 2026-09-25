"""Variante de elección de `cloze_original`: la misma frase tapada, con cuatro
opciones en lugar de escribir la palabra (D-022).

Es un tipo nuevo que contiene un `ClozeOriginal`, no un cambio en él: la
variante de escritura sigue siendo determinista y de dos campos (D-019). Aquí
las opciones y su orden no se pueden derivar de la frase y la palabra, porque
dependen del corpus y del azar, así que se fijan al crear el ejercicio y se
guardan.
"""

from dataclasses import dataclass

from vocab.domain.exercises.cloze_original import ClozeOriginal

# La respuesta y tres distractores. Con menos, la probabilidad de acertar al
# azar sube del 25 % y los resultados dejan de ser comparables.
OPTION_COUNT = 4


@dataclass(frozen=True)
class ClozeOriginalChoice:
    """Un `ClozeOriginal` y sus opciones, en el orden en que se muestran."""

    cloze: ClozeOriginal
    options: tuple[str, ...]

    def __post_init__(self) -> None:
        # Invariantes y no decisiones al nacer, como en `ClozeOriginal`: se
        # comprueban también al reconstruir el ejercicio en F1.
        lowered = [option.lower() for option in self.options]
        if len(self.options) != OPTION_COUNT:
            raise ValueError(
                f"hacen falta {OPTION_COUNT} opciones, no {len(self.options)}"
            )
        if len(set(lowered)) != len(lowered):
            raise ValueError("hay opciones repetidas")
        if self.cloze.answer.lower() not in lowered:
            raise ValueError(f"«{self.cloze.answer}» no está entre las opciones")

    def is_correct(self, response: str) -> bool:
        """La misma corrección que la variante de escritura: en minúscula."""
        return self.cloze.is_correct(response)
