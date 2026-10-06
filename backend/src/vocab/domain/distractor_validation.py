"""Validadores deterministas de los distractores de `mcq_definition` (§6.1).

Comprueban, frente a la definición correcta, lo que se puede decidir sin un
modelo sobre los tres distractores que devuelve el generador (A1). Cada fallo es
un código y un índice, sin texto: el informe se guardará y se contará en F2, y
el texto que lea el modelo en el reintento depende del idioma del prompt, que se
decide en el bucle.

Cada código, con su métrica de §6.1:

- `EMPTY`, comprobación básica sin métrica propia: el distractor no tiene
  ningún token.
- `DUPLICATE`, comprobación básica sin métrica propia: repite los tokens de un
  distractor anterior. Se marca el posterior.
- `OVERLAPS_CORRECT`, D1 (filtración léxica): la definición correcta aparece
  contigua dentro del distractor, o al revés; la igualdad está incluida.
- `NEGATION`, D7 (distractores no triviales): el distractor niega y la
  definición correcta no.

D2, la homogeneidad gramatical, necesita spaCy y no está aquí.

**Tokens, no caracteres.** Todo se compara como secuencias de tokens: texto en
forma NFC y en minúsculas, el apóstrofo tipográfico (’) convertido en recto,
piezas hechas de letras y dígitos de cualquier alfabeto y de apóstrofos, y sin
los apóstrofos de los bordes, que hacen de comillas: «'Not able'» da `not`, no
`'not`. Los de dentro se quedan (`doesn't`). Una palabra con tilde o ñ es un
solo token: `café` no se parte en `caf`. Comparar subcadenas de caracteres es
la trampa de D-019: `to rest` está dentro de `to restore`.

**El idioma es un dato** (§3.3.1). La tokenización vale para cualquier
alfabeto. Lo único que depende del idioma son los marcadores de negación,
indexados por idioma como la lista de ruido (D-013). Añadir un idioma consiste
en añadir su lista en `NEGATION_MARKERS`: sus palabras y, si las tiene, sus
terminaciones de negación. A diferencia de la lista de ruido, que con un idioma
sin lista no marca nada, aquí un idioma sin lista da `ValueError`: sin
marcadores, D7 daría por bueno cualquier distractor que niegue.

**Límites conocidos**, terreno del juez en F4:

- D7 no ve antónimos léxicos. Busca marcadores de negación, no significados
  opuestos: `fragile` frente a `resilient`, o «Prone to breaking down under
  pressure» frente a «able to recover quickly from hardship», pasan. Un
  distractor así se descarta sin conocer la palabra, y eso lo mide J2
  (plausibilidad de distractores).
- D1 no ve paráfrasis. «recovers fast after difficulties» dice lo mismo que la
  definición correcta sin compartir con ella una secuencia de tokens, y deja
  dos opciones defendibles: lo mide J1 (unicidad de la respuesta).
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

# Letras y dígitos de cualquier alfabeto (`\w` sin el guion bajo) y apóstrofos.
# Con texto en inglés, lo mismo que `[a-z0-9']` tras pasar a minúsculas.
TOKEN = re.compile(r"(?:[^\W_]|')+")


@dataclass(frozen=True)
class NegationMarkers:
    """Lo que niega en un idioma: palabras sueltas y terminaciones de token.

    Las terminaciones son parte de la lista del idioma, no una regla aparte:
    `n't` es inglés, y aplicada a otro idioma sería una regla ajena.
    """

    words: frozenset[str]
    suffixes: tuple[str, ...] = ()


# Listas cerradas, como la de ruido (D-013): solo marcan lo que está escrito
# aquí, y se auditan abriendo el archivo. Sin prefijos privativos, aunque D-005
# los preveía: un `in-` o un `un-` marcaría `interesting`, `under` o `uniform`.
NEGATION_MARKERS: dict[str, NegationMarkers] = {
    "en": NegationMarkers(
        words=frozenset(
            {
                "not",
                "no",
                "never",
                "none",
                "nothing",
                "neither",
                "nor",
                "without",
                "lack",
                "lacks",
                "lacking",
                "unable",
                "incapable",
                "inability",
                "cannot",
                "absence",
                "absent",
                "devoid",
                "fail",
                "fails",
                "failing",
            }
        ),
        # `doesn't`, `can't`, `won't`.
        suffixes=("n't",),
    ),
}

Tokens = tuple[str, ...]


class ViolationCode(StrEnum):
    """Qué comprobación falló. Los valores se guardarán en F2, así que se
    escriben a mano: renombrar un miembro no debe cambiar lo guardado."""

    EMPTY = "empty"
    DUPLICATE = "duplicate"
    OVERLAPS_CORRECT = "overlaps_correct"
    NEGATION = "negation"


@dataclass(frozen=True)
class Violation:
    """Un fallo de un distractor: qué comprobación y en cuál de los tres
    (`distractor_index`, 0, 1 o 2, en el orden en que llegaron)."""

    code: ViolationCode
    distractor_index: int


def validate_distractors(
    correct_definition: str, distractors: tuple[str, str, str], lang: str
) -> tuple[Violation, ...]:
    """Todas las violaciones de los tres distractores; la tupla vacía
    significa válido.

    No se para en la primera: el reintento tiene que poder contar al modelo
    todo lo que falló, y F2 contará cada código. El orden es el de las
    comprobaciones (vacío, duplicado, D1, D7) y, dentro de cada una, el de los
    distractores.

    Dos errores de quien llama, no distractores malos, se rechazan con
    `ValueError`:

    - Un idioma sin lista de marcadores.
    - Una definición correcta sin tokens: la secuencia vacía está en todas, y
      D1 marcaría los tres. Es el mismo criterio que la palabra vacía de
      `ClozeOriginal` (D-019).
    """
    markers = NEGATION_MARKERS.get(lang)
    if markers is None:
        raise ValueError(
            f"No hay marcadores de negación para el idioma {lang!r}: "
            "añade su lista en NEGATION_MARKERS."
        )
    correct = _tokens(correct_definition)
    if not correct:
        raise ValueError(
            f"La definición correcta no tiene tokens: {correct_definition!r}"
        )
    candidates = tuple(_tokens(distractor) for distractor in distractors)

    return (
        *_empty(candidates),
        *_duplicates(candidates),
        *_overlaps_correct(correct, candidates),
        *_negations(correct, candidates, markers),
    )


def _tokens(text: str) -> Tokens:
    """La normalización común: ver «Tokens, no caracteres» en el módulo.

    NFC antes que nada: una tilde puede llegar como carácter aparte (NFD), que
    no es letra y partiría la palabra.
    """
    normalized = unicodedata.normalize("NFC", text).lower().replace("’", "'")
    pieces = TOKEN.findall(normalized)
    stripped = (piece.strip("'") for piece in pieces)
    return tuple(token for token in stripped if token)


def _empty(candidates: tuple[Tokens, ...]) -> list[Violation]:
    """Distractores sin ningún token: vacíos o hechos solo de puntuación."""
    return [
        Violation(ViolationCode.EMPTY, index)
        for index, tokens in enumerate(candidates)
        if not tokens
    ]


def _duplicates(candidates: tuple[Tokens, ...]) -> list[Violation]:
    """Distractores con los mismos tokens que uno anterior. Se marca el
    posterior: el primero sigue siendo un distractor válido."""
    return [
        Violation(ViolationCode.DUPLICATE, index)
        for index, tokens in enumerate(candidates)
        if tokens in candidates[:index]
    ]


def _overlaps_correct(
    correct: Tokens, candidates: tuple[Tokens, ...]
) -> list[Violation]:
    """D1: la definición correcta dentro del distractor, o el distractor dentro
    de la definición correcta.

    No se aplica a los vacíos: la secuencia vacía está contenida en todas, y
    ya los marca `EMPTY`.
    """
    return [
        Violation(ViolationCode.OVERLAPS_CORRECT, index)
        for index, tokens in enumerate(candidates)
        if tokens and (_contains(tokens, correct) or _contains(correct, tokens))
    ]


def _negations(
    correct: Tokens, candidates: tuple[Tokens, ...], markers: NegationMarkers
) -> list[Violation]:
    """D7: distractores que niegan, cuando la definición correcta no niega.

    Si la correcta también niega («having no known name»), la negación no
    distingue a ningún distractor, así que no lo delata.
    """
    if _negates(correct, markers):
        return []
    return [
        Violation(ViolationCode.NEGATION, index)
        for index, tokens in enumerate(candidates)
        if _negates(tokens, markers)
    ]


def _contains(haystack: Tokens, needle: Tokens) -> bool:
    """Si `needle` aparece contigua dentro de `haystack`, como secuencia de
    tokens."""
    size = len(needle)
    return any(
        haystack[start : start + size] == needle
        for start in range(len(haystack) - size + 1)
    )


def _negates(tokens: Tokens, markers: NegationMarkers) -> bool:
    # `endswith` admite una tupla; con la tupla vacía, nunca casa.
    return any(
        token in markers.words or token.endswith(markers.suffixes) for token in tokens
    )
