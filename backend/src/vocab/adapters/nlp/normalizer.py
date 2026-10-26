"""Normalización lingüística con spaCy: lema, categoría gramatical, rasgos y
partícula.

Implementa `ports.normalizer.Normalizer`. El lema y la categoría de una
palabra dependen de su frase.

Todo lo que sabe de spaCy vive en este paquete: qué modelo corresponde a cada
idioma, cuándo se carga, qué token de la frase es la palabra consultada y qué
forma tienen las tuplas que espera `nlp.pipe`. La guarda de unidad léxica
(`lexical_unit.particle_of`) se aplica aquí, sobre el mismo token y en la misma
pasada (D-008).
"""

from collections import defaultdict
from collections.abc import Iterator
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Token

from vocab.adapters.nlp.lexical_unit import particle_of
from vocab.ports.normalizer import CleanedLookup, NormalizedWord

MODELS = {"en": "en_core_web_sm"}


@lru_cache(maxsize=4)
def _load_model(lang: str) -> Language:
    """Carga perezosa y cacheada: el modelo pesa y no debe cargarse al importar."""
    return spacy.load(MODELS[lang], exclude=["ner"])


def normalize(data: list[CleanedLookup]) -> list[NormalizedWord]:
    """Analiza las consultas y devuelve su palabra normalizada.

    Acepta idiomas mezclados: se agrupan y cada grupo se procesa con su
    modelo. Ese agrupamiento es lo que hace que la salida no conserve el orden
    de la entrada — el puerto no lo promete, y quien llama reempareja por
    `external_id`.
    """
    by_language: dict[str, list[CleanedLookup]] = defaultdict(list)
    for item in data:
        by_language[item.lang].append(item)

    result: list[NormalizedWord] = []
    for lang, group in by_language.items():
        result.extend(_normalize_group(group, lang))
    return result


def _as_pipe_input(
    group: list[CleanedLookup],
) -> Iterator[tuple[str, CleanedLookup]]:
    """`nlp.pipe(as_tuples=True)` quiere (texto, contexto) en ese orden.

    La tupla se construye aquí: es una exigencia de spaCy, no del puerto, y
    por eso `CleanedLookup` ya no necesita tener forma de tupla.
    """
    return ((item.clean_sentence, item) for item in group)


def _normalize_group(group: list[CleanedLookup], lang: str) -> list[NormalizedWord]:
    nlp = _load_model(lang)
    result: list[NormalizedWord] = []

    for doc, item in nlp.pipe(_as_pipe_input(group), as_tuples=True):
        token = _first_occurrence(doc, item.word)
        if token is None:
            # Token no localizado: se degrada a la palabra en minúsculas y se
            # marca con `pos`, `morph` y `particle` a `None`. Nunca se descarta
            # — el puerto promete un resultado por entrada.
            result.append(
                NormalizedWord(
                    external_id=item.external_id,
                    lemma=item.word.lower(),
                    pos=None,
                    morph=None,
                    particle=None,
                )
            )
        else:
            result.append(
                NormalizedWord(
                    external_id=item.external_id,
                    lemma=token.lemma_.lower(),
                    pos=token.pos_,
                    morph=str(token.morph),
                    particle=particle_of(token),
                )
            )

    return result


def _first_occurrence(doc: Doc, word: str) -> Token | None:
    """La palabra consultada dentro de su frase: la primera aparición, por
    texto en minúsculas.

    La comparten el normalizador y la guarda de unidad léxica. Tiene que ser
    una sola función: si cada uno buscara a su manera, en las frases que
    repiten la palabra `pos`/`morph` y la guarda hablarían de tokens distintos.
    """
    target = word.lower()
    return next((token for token in doc if token.text.lower() == target), None)
