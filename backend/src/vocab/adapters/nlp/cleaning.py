"""Limpieza determinista de las frases de contexto del Kindle.

Sin dependencias de NLP. Los patrones salen
de lo medido sobre el corpus real en el notebook correspondiente.

Se ejecuta antes de spaCy.
"""

import re

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


def clean_sentence(raw: str) -> str:
    """Elimina la suciedad de maquetación sin alterar el texto del autor."""
    text = raw.translate(INVISIBLE_CHARS)
    text = FOOTNOTE_REFERENCE.sub("", text)
    text = TRAILING_BRACKET.sub("", text)
    text = MULTIPLE_SPACES.sub(" ", text)
    return text.strip()


def is_truncated(cleaned: str) -> bool:
    """Una frase cortada a mitad no termina en puntuación de cierre."""
    return not cleaned.endswith(SENTENCE_ENDINGS)
