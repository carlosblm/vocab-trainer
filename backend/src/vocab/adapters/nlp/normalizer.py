"""Normalización lingüística con spaCy: lema y categoría gramatical.

El lema y la categoría de una palabra dependen de su frase: `saw` es el
pasado de *ver* o una herramienta según el contexto. Por eso se analiza la
frase completa y de ella se extrae el token consultado.

Se ejecuta DESPUÉS de `cleaning.clean_sentence`: un segmentador que recibe
`...more.[59].[` detecta dos oraciones donde hay una.
"""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import spacy
from spacy.language import Language

from vocab.ports.importer import RawLookup

MODELS = {"en": "en_core_web_sm"}

# Marca la palabra cuyo token no se localizó en su frase.
UNRESOLVED_POS = "X"


@lru_cache(maxsize=4)
def _load_model(lang: str) -> Language:
    """Carga perezosa y cacheada: el modelo pesa y no debe cargarse al importar."""
    return spacy.load(MODELS[lang], exclude=["ner"])


@dataclass(frozen=True)
class NormalizedWord:
    """Resultado de analizar una palabra dentro de su frase."""

    lemma: str
    pos: str
    tag: str

    @property
    def is_resolved(self) -> bool:
        return self.pos != UNRESOLVED_POS


class CleanedLookup(NamedTuple):
    """Una consulta con su frase ya limpia. El texto va primero: es el
    orden que espera `nlp.pipe(..., as_tuples=True)`."""

    clean_sentence: str
    lookup: RawLookup


def normalize(
    data: list[CleanedLookup],
) -> list[tuple[RawLookup, NormalizedWord]]:
    """Analiza las consultas y devuelve cada una con su palabra normalizada.

    Acepta idiomas mezclados: se agrupan y cada grupo se procesa con su
    modelo. Ninguna consulta se pierde; las que no se resuelven vuelven
    marcadas con `UNRESOLVED_POS`.
    """
    by_language: dict[str, list[CleanedLookup]] = defaultdict(list)
    for item in data:
        by_language[item.lookup.lang].append(item)

    result: list[tuple[RawLookup, NormalizedWord]] = []
    for lang, group in by_language.items():
        result.extend(_normalize_group(group, lang))
    return result


def _normalize_group(
    group: list[CleanedLookup], lang: str
) -> list[tuple[RawLookup, NormalizedWord]]:
    nlp = _load_model(lang)
    result: list[tuple[RawLookup, NormalizedWord]] = []

    for doc, lookup in nlp.pipe(group, as_tuples=True):
        target = lookup.word.lower()
        for token in doc:
            if token.text.lower() == target:
                result.append(
                    (
                        lookup,
                        NormalizedWord(
                            lemma=token.lemma_.lower(),
                            pos=token.pos_,
                            tag=token.tag_,
                        ),
                    )
                )
                break
        else:
            result.append(
                (
                    lookup,
                    NormalizedWord(
                        lemma=lookup.word.lower(),
                        pos=UNRESOLVED_POS,
                        tag=UNRESOLVED_POS,
                    ),
                )
            )

    return result
