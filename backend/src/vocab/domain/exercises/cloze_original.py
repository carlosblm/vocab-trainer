"""Ejercicio `cloze_original`: la frase real del libro con la palabra tapada.

Determinista: queda definido por la frase y la palabra, sin azar ni posición
que guardar, porque se tapan todas las apariciones. Tapar solo una dejaría la
respuesta a la vista en las frases que repiten la palabra (D-019).
"""

import re
from dataclasses import dataclass

# Longitud fija, igual para todos los ejercicios: un hueco del tamaño de la
# palabra revelaría cuántas letras tiene.
BLANK = "_____"


def _whole_word(word: str) -> re.Pattern[str]:
    """Patrón que localiza `word` como palabra completa, sin distinguir
    mayúsculas.

    - Lookarounds sobre `\\w` y no `\\b`: `\\b` falla si la palabra empieza o
      termina en un carácter que no es de palabra. En el corpus no hay ninguna
      así, pero la definición no debe depender de eso.
    - `re.escape`: la palabra es un dato, nunca un patrón. Sin escapar, `U.S.`
      encajaría con `UKS.`.
    - El guion no es `\\w`, así que cuenta como borde: `savvy` se localiza en
      `tech-savvy`. Es la palabra que guardó la fuente, no el compuesto.
    """
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class ClozeOriginal:
    """La frase limpia de un contexto con la palabra consultada tapada.

    Solo guarda lo que define el ejercicio. El texto tapado y la respuesta se
    derivan, así que no se puede representar un ejercicio cuyo hueco no
    corresponda a su frase. La tabla `exercises` de F1 podrá persistir estos
    dos campos y reconstruir el resto.

    `sentence` es la frase limpia, no la cruda: es lo que se muestra tras un
    fallo. `word` es la forma consultada en ese contexto, tal como la guardó la
    fuente (`Context.term`, D-020), no el término de la entrada.
    """

    sentence: str
    word: str

    def __post_init__(self) -> None:
        # Es un invariante, no una decisión al nacer: también tiene que
        # cumplirse al reconstruir el ejercicio en F1. Por eso va aquí y no en
        # una fábrica como `Entry.new`, que decide algo una sola vez (D-018).
        # Se lanza en vez de devolver un ejercicio vacío: uno sin nada tapado
        # enseña la respuesta, y ese es el peor fallo silencioso posible.
        if not self.word.strip():
            # Sin esta guarda el patrón vacío encaja entre dos caracteres que
            # no son de palabra, tapa la nada e `is_correct("")` da True.
            raise ValueError("la palabra del ejercicio está vacía")
        if _whole_word(self.word).search(self.sentence) is None:
            raise ValueError(
                f"«{self.word}» no aparece como palabra completa en la frase"
            )

    @property
    def masked_sentence(self) -> str:
        """La frase con todas las apariciones de la palabra tapadas."""
        return _whole_word(self.word).sub(BLANK, self.sentence)

    @property
    def answer(self) -> str:
        """La forma tal como aparece en la frase, no el lema.

        Si la palabra se repite con mayúsculas distintas (`Biases … biases`),
        es la primera aparición. Para corregir da igual: se compara en
        minúsculas.
        """
        match = _whole_word(self.word).search(self.sentence)
        assert match is not None, "__post_init__ garantiza que la palabra aparece"
        return match.group(0)

    def is_correct(self, response: str) -> bool:
        """Compara sin mayúsculas ni espacios en los extremos, y nada más."""
        return response.strip().lower() == self.answer.lower()
