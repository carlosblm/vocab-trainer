"""Puerto de normalización: interfaz que toda normalización lingüística
debe cumplir.

El lema y la categoría de una palabra dependen de la frase donde aparece, no
de la palabra aislada (D-015). Este puerto describe esa operación.

Garantías del contrato, que todo adaptador debe respetar:

- **Un resultado por cada entrada.** `len(salida) == len(entrada)`. Una
  consulta cuyo token no se localiza vuelve con `pos = None`; no se omite. Un
  adaptador que descarta entradas rompe el contrato: el caso de uso perdería
  vocabulario sin enterarse.
- **Emparejados por `external_id`, sin garantía de orden.** La salida puede
  venir en cualquier orden — el único adaptador de hoy agrupa por idioma y
  concatena, así que con idiomas mezclados ya no lo conserva. Quien llame
  reempareja por la clave, nunca por la posición.
- **Las frases llegan limpias.** El tipo `CleanSentence` lo impone: es la
  precondición de `domain.cleaning`, no una recomendación. Un segmentador que
  recibe notas al pie ve dos oraciones donde hay una.
"""

from collections.abc import Callable
from dataclasses import dataclass

from vocab.domain.cleaning import CleanSentence


@dataclass(frozen=True)
class CleanedLookup:
    """Lo que la normalización necesita de una consulta, y nada más..
    `external_id` viaja solo para poder reemparejar el resultado.
    """

    external_id: str
    word: str
    lang: str
    clean_sentence: CleanSentence


@dataclass(frozen=True)
class NormalizedWord:
    """Resultado de analizar una palabra dentro de su frase.

    `pos = None` significa que el token no se localizó en la frase. En ese
    caso `lemma` es la palabra consultada en minúsculas: se degrada, no se
    pierde.
    """

    external_id: str
    lemma: str
    pos: str | None

    @property
    def is_resolved(self) -> bool:
        return self.pos is not None


# El contrato es un `Callable` y no un `Protocol`: a diferencia de
# `VocabularyImporter` (ruta, idiomas) y `VocabularyRepository` (sesión), una
# normalización no tiene estado que inyectar. Exigir una clase obligaría al
# adaptador a envolver una función en un objeto vacío, y a los tests a
# fabricar una clase donde basta un cierre.
Normalizer = Callable[[list[CleanedLookup]], list[NormalizedWord]]
