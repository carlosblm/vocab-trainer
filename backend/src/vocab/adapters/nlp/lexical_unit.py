"""Guarda de unidad léxica (D-008): si la palabra consultada lleva partícula.

La regla es sintáctica: la palabra tiene un dependiente con la relación `prt`,
pegado a ella («eased out the hydraulics») o separado por el objeto («eased the
hydraulics out»). Vive en el adaptador porque depende del esquema de etiquetas
del modelo: `prt` es la etiqueta de `en_core_web_sm`; en Universal Dependencies
la misma relación se llama `compound:prt`.

Límite conocido: la sintaxis no ve la opacidad. «came across an old letter»
(encontrar) y «came across an old bridge» (cruzar) reciben el mismo análisis,
con `across` como preposición, y ninguno se marca.

La aplica el normalizador, sobre el mismo token del que salen `pos` y `morph` y
en la misma pasada: la partícula viaja en `NormalizedWord.particle` y se guarda
con el contexto (D-033). `detect_particles` queda como vista por lotes de esa
misma pasada, para el script de medición de D-025 y sus tests.
"""

from spacy.tokens import Token

from vocab.ports.normalizer import CleanedLookup

PARTICLE = "prt"


def particle_of(token: Token) -> str | None:
    """Núcleo de la regla: el primer dependiente `prt` de la palabra, en
    cualquier posición, en minúsculas; o `None`.

    Se miran los hijos y no la palabra siguiente porque la partícula separada
    sigue colgando del verbo. Y no se exige que el objeto cuelgue del verbo
    como `dobj`: en la frase real de `eased out hydraulics` el analizador marca
    `out` como `prt` pero cuelga `hydraulics` de `out` como `pobj`.

    En minúsculas, igual que el lema, porque las dos piezas forman el nombre de
    la unidad: `ease` + `out`.
    """
    particle = next((child for child in token.children if child.dep_ == PARTICLE), None)
    return particle.lower_ if particle is not None else None


def detect_particles(data: list[CleanedLookup]) -> dict[str, str | None]:
    """Devuelve, por `external_id`, la partícula de la palabra consultada o `None`.

    Es la partícula del normalizador, sin el resto del análisis: una sola
    implementación de la regla y de la localización del token. `None` también
    cuando la palabra no se localiza en su frase.
    """
    # Importación local: el normalizador importa `particle_of` de este módulo,
    # y arriba cerraría un ciclo entre los dos.
    from vocab.adapters.nlp.normalizer import normalize

    return {word.external_id: word.particle for word in normalize(data)}
