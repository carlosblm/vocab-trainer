"""Qué definición puede enseñar un contexto: la política de D-025.

`mcq_definition` muestra una definición como la respuesta correcta. Si es la de
otro sentido, otro lema u otra palabra, el ejercicio enseña un significado
falso: el daño de D-008. Este módulo decide cuándo hay una definición segura y,
si no la hay, por qué. Sin ella, el contexto se queda con `cloze_original`, que
siempre está disponible (D-025).

Separa los hechos de la decisión. `LexiconFacts` es lo que el léxico sabe de un
contexto, sin interpretar, y lo produce el adaptador del léxico.
`decide_definition` aplica la política sobre esos hechos. Así la política se
prueba sin léxico, y cambiar de léxico no la toca.

Toda comparación de lemas se hace en minúsculas, como en la medición de D-025.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Sense:
    """Un sentido del léxico: su identificador y su glosa, la definición que
    se enseñaría."""

    id: str
    gloss: str


@dataclass(frozen=True)
class LexiconFacts:
    """Lo que el léxico sabe de un contexto, sin decidir nada.

    - `pos_supported`: si la categoría del contexto tiene equivalente en el
      léxico. Si no, los otros dos campos van vacíos.
    - `term_lemmas`: los lemas, en minúsculas, a los que el léxico lleva la
      forma consultada en esa categoría.
    - `senses`: los sentidos del lema de la entrada en esa categoría, en el
      orden del léxico.
    """

    pos_supported: bool
    term_lemmas: frozenset[str]
    senses: tuple[Sense, ...]


class DefinitionStatus(StrEnum):
    """Si el contexto tiene una definición segura y, si no, por qué.

    Los valores se guardarán, así que se escriben a mano: renombrar un
    miembro no debe cambiar lo guardado.
    """

    ELIGIBLE = "eligible"
    POS_UNMAPPED = "pos_unmapped"
    FORM_NOT_FOUND = "form_not_found"
    LEMMA_DISAGREES = "lemma_disagrees"
    LEXICAL_UNIT = "lexical_unit"
    POLYSEMOUS = "polysemous"


@dataclass(frozen=True)
class DefinitionDecision:
    """El estado y, solo si es `ELIGIBLE`, la definición y el sentido del que
    sale. `sense_id` viaja para poder rastrear qué sentido se enseñó."""

    status: DefinitionStatus
    definition: str | None = None
    sense_id: str | None = None

    def __post_init__(self) -> None:
        # Una definición sin el estado que la autoriza, o al revés, es
        # justo lo que esta política existe para impedir.
        eligible = self.status is DefinitionStatus.ELIGIBLE
        if eligible != (self.definition is not None and self.sense_id is not None):
            raise ValueError(
                f"La definición y el sentido van juntos y solo con ELIGIBLE: {self!r}"
            )


def decide_definition(
    lemma: str, particle: str | None, facts: LexiconFacts
) -> DefinitionDecision:
    """La política de D-025 sobre los hechos de un contexto.

    `lemma` es el de la entrada (`Entry.lemma`), y `particle`, la de R1 o
    `None`. El primer estado que cumple, en este orden:

    1. La categoría no tiene equivalente en el léxico: `POS_UNMAPPED`.
    2. La forma consultada no lleva a ningún lema: `FORM_NOT_FOUND`.
    3. Los lemas del léxico no son exactamente `{lemma}`: `LEMMA_DISAGREES`.
       Falte el lema o venga acompañado, el léxico no confirma que la palabra
       de la frase sea la de la entrada (D-015).
    4. Hay partícula (R1, D-008): `LEXICAL_UNIT`, esté o no la unidad en el
       léxico. Sin ella no se vuelve a la palabra sola, porque `belly-up`
       enseñaría «vientre». Con ella tampoco basta un único sentido: el único
       de `chew up` en `oewn:2025` es «censure severely or angrily», y es falso
       en la frase de la exportación de septiembre de 2026 donde aparece.
       Elegir el sentido de una unidad es la selección de sentido de F4.
    5. Un único sentido: `ELIGIBLE`, con su glosa y su identificador.
    6. Varios sentidos: `POLYSEMOUS`. Elegir uno es la selección de sentido de
       F4.

    Con el lema confirmado, el lema está en el léxico y tiene al menos un
    sentido. Si `senses` llega vacío, los hechos se contradicen y se lanza
    `ValueError`: es un fallo del adaptador, no un estado del contexto.
    """
    if not facts.pos_supported:
        return DefinitionDecision(DefinitionStatus.POS_UNMAPPED)
    if not facts.term_lemmas:
        return DefinitionDecision(DefinitionStatus.FORM_NOT_FOUND)
    if facts.term_lemmas != {lemma.lower()}:
        return DefinitionDecision(DefinitionStatus.LEMMA_DISAGREES)
    if particle is not None:
        return DefinitionDecision(DefinitionStatus.LEXICAL_UNIT)

    match facts.senses:
        case (sense,):
            return DefinitionDecision(
                DefinitionStatus.ELIGIBLE, definition=sense.gloss, sense_id=sense.id
            )
        case ():
            raise ValueError(
                f"Hechos incoherentes: el léxico lleva la forma a {lemma!r}, "
                "pero no le da ningún sentido."
            )
        case _:
            return DefinitionDecision(DefinitionStatus.POLYSEMOUS)
