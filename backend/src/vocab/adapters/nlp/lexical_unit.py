"""Guarda de unidad léxica (D-008): si la palabra consultada lleva partícula.

La regla es sintáctica: la palabra tiene un dependiente con la relación `prt`,
pegado a ella («eased out the hydraulics») o separado por el objeto («eased the
hydraulics out»). Vive en el adaptador porque depende del esquema de etiquetas
del modelo: `prt` es la etiqueta de `en_core_web_sm`; en Universal Dependencies
la misma relación se llama `compound:prt`.

Límite conocido: la sintaxis no ve la opacidad. «came across an old letter»
(encontrar) y «came across an old bridge» (cruzar) reciben el mismo análisis,
con `across` como preposición, y ninguno se marca.

Sin consumidor hasta F1 (`mcq_definition`): no hay puerto ni se guarda nada.
"""

from collections import defaultdict

from spacy.tokens import Token

# Del normalizador se reutilizan el cargador, para compartir su caché y cargar
# el modelo una sola vez por proceso, y la localización de la palabra, para que
# la guarda mire el mismo token del que salen `pos` y `morph`.
from vocab.adapters.nlp.normalizer import _first_occurrence, _load_model
from vocab.ports.normalizer import CleanedLookup

PARTICLE = "prt"


def detect_particles(data: list[CleanedLookup]) -> dict[str, str | None]:
    """Devuelve, por `external_id`, la partícula de la palabra consultada o `None`.

    Un resultado por consulta, emparejado por la clave como en el normalizador.
    `None` también cuando la palabra no se localiza en su frase: la guarda no
    puede decir nada, y ese caso ya lo distingue `NormalizedWord.pos = None`.

    La partícula va en minúsculas, igual que el lema, porque las dos piezas
    forman el nombre de la unidad: `ease` + `out`.
    """
    by_language: dict[str, list[CleanedLookup]] = defaultdict(list)
    for item in data:
        by_language[item.lang].append(item)

    result: dict[str, str | None] = {}
    for lang, group in by_language.items():
        nlp = _load_model(lang)
        pairs = ((item.clean_sentence, item) for item in group)
        for doc, item in nlp.pipe(pairs, as_tuples=True):
            token = _first_occurrence(doc, item.word)
            particle = _particle(token) if token is not None else None
            result[item.external_id] = particle.lower_ if particle is not None else None
    return result


def _particle(token: Token) -> Token | None:
    """Núcleo de la regla: el primer dependiente `prt` de la palabra, en
    cualquier posición.

    Se miran los hijos y no la palabra siguiente porque la partícula separada
    sigue colgando del verbo. Y no se exige que el objeto cuelgue del verbo
    como `dobj`: en la frase real de `eased out hydraulics` el analizador marca
    `out` como `prt` pero cuelga `hydraulics` de `out` como `pobj`.
    """
    return next((child for child in token.children if child.dep_ == PARTICLE), None)
