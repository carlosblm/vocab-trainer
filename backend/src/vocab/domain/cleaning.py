"""Limpieza determinista de las frases de contexto.

Sin dependencias de NLP. Los patrones salen de lo medido sobre el corpus real
en el notebook correspondiente.

Se ejecuta antes de spaCy: un segmentador que recibe `...more.[59].[` detecta
dos oraciones donde hay una. `CleanSentence` existe para que ese orden deje de
ser una convención y pase a ser una condición de tipo.
"""

import re
from typing import NewType

# Una frase ya limpia. `NewType` y no un alias: con un alias, `str` y
# `CleanSentence` serían el mismo tipo y mypy no diría nada al colar una frase
# cruda en el normalizador. Ese error no rompe nada — produce un lema peor
# (D-015), que es justo el fallo silencioso que conviene que no compile.
#
# Límite: `NewType` se borra en tiempo de ejecución. Frena el descuido, no la
# intención; `CleanSentence(raw)` sigue siendo legal y una frase leída de
# Postgres vuelve como `str` y hay que reetiquetarla a mano.
CleanSentence = NewType("CleanSentence", str)

# Referencia a nota al pie intercalada: [59], [102].
FOOTNOTE_REFERENCE = re.compile(r"\[\d+\]")

# Corchete de apertura huérfano al final. 17 de las 31 frases sin puntuación
# reconocible terminan así: la frase está completa y el corchete es el inicio
# de una llamada a nota al pie que se coló en el recorte.
TRAILING_BRACKET = re.compile(r"\s*\[\s*$")

MULTIPLE_SPACES = re.compile(r"\s{2,}")

# Invisibles que arrastra el volcado del libro.
INVISIBLE_CHARS = str.maketrans(
    {
        "\xa0": " ",  # espacio no separable
        "\u2009": " ",  # espacio fino
        "\u200b": "",  # ancho cero
        "\ufeff": "",  # marca de orden de bytes
    }
)

SENTENCE_ENDINGS = (".", "!", "?", "…", "”", "’", "»", '"', ")")


def clean_sentence(raw: str) -> CleanSentence:
    """Elimina la suciedad de maquetación sin alterar el texto del autor.

    Es la única fábrica de `CleanSentence`.
    """
    text = raw.translate(INVISIBLE_CHARS)
    text = FOOTNOTE_REFERENCE.sub("", text)
    text = TRAILING_BRACKET.sub("", text)
    text = MULTIPLE_SPACES.sub(" ", text)
    return CleanSentence(text.strip())


def is_truncated(cleaned: CleanSentence) -> bool:
    """Una frase cortada a mitad no termina en puntuación de cierre."""
    return not cleaned.endswith(SENTENCE_ENDINGS)
