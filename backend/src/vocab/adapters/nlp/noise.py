"""Filtrado del ruido de consulta: pulsaciones accidentales sobre palabras
funcionales al pasar página.

Determinista y auditable: una lista cerrada por idioma, no una regla sobre la
categoría gramatical que devuelve spaCy. El motivo es el sentido del error. Un
filtro por categoría descarta en silencio vocabulario que el modelo etiquetó
mal; una lista solo puede descartar lo que está escrito en ella, y se audita
abriendo el archivo.

La lista es deliberadamente corta: solo palabras del núcleo básico que ningún
lector de nivel intermedio consultaría a propósito. Quedan fuera dos grupos:

- Funcionales con acepción de contenido. `even` aparece en el corpus dentro de
  «Never give roses in even numbers», donde significa *par*. Lo mismo con
  `can`, `will`, `may`, `might`, `must`, `mine`, `own`, `well`, `like`, `just`,
  `still`, `back`, `right`, `kind`.
- Funcionales que sí son vocabulario para un hispanohablante. `beneath`,
  `neither`, `shall`, `although`, `whereas`, `despite` y `throughout` están
  consultadas en el corpus real y son consultas deliberadas, no accidentes.

Prefiere colar ruido, que el usuario ignora en un repaso, a perder vocabulario
que quería estudiar y que desaparecería sin dejar rastro.
"""

STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        {
            # Artículos y demostrativos
            "a",
            "an",
            "the",
            "this",
            "that",
            "these",
            "those",
            # Preposiciones básicas
            "of",
            "in",
            "on",
            "at",
            "to",
            "from",
            "with",
            "by",
            "for",
            # Conjunciones y comparativos
            "and",
            "or",
            "but",
            "if",
            "so",
            "as",
            "than",
            # Pronombres personales y posesivos
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
            "my",
            "your",
            "his",
            "its",
            "our",
            "their",
            "who",
            "which",
            "what",
            # Auxiliares
            "am",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            # Adverbios y cuantificadores básicos
            "not",
            "no",
            "very",
            "too",
            "also",
            "then",
            "there",
            "here",
            "all",
            "some",
            "more",
            "most",
            "much",
            "many",
            "when",
            "how",
        }
    ),
}

# Una sola letra nunca es vocabulario: en el corpus aparecen `A` y `M`,
# tocadas al pasar página sobre una inicial o una sigla partida.
MIN_LENGTH = 2


def is_noise(word: str, lang: str) -> bool:
    """Si la palabra consultada es una pulsación accidental, no vocabulario."""
    cleaned = word.strip()
    if len(cleaned) < MIN_LENGTH:
        return True
    return cleaned.lower() in STOPWORDS.get(lang, frozenset())
