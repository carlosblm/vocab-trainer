"""Puerto del léxico: lo que una fuente de definiciones sabe de cada contexto.

Devuelve hechos, no decisiones. Qué definición se puede enseñar lo decide
`domain.definition_policy` sobre esos hechos, y quien llama no sabe qué léxico
hay detrás (D-025).

Garantías del contrato, las mismas que las del normalizador (D-016):

- **Un resultado por consulta.** Una consulta que el léxico no conoce vuelve
  con hechos vacíos, no se omite.
- **Emparejados por `external_id`.** La salida es un diccionario por esa
  clave; quien llama reempareja por ella, nunca por la posición.
- **Por lotes.** Una llamada por lote de contextos, como el normalizador y la
  guarda de unidad léxica, que trabajan sobre los mismos contextos.
"""

from dataclasses import dataclass
from typing import Protocol

from vocab.domain.definition_policy import LexiconFacts


@dataclass(frozen=True)
class LexiconQuery:
    """Lo que el léxico necesita de un contexto.

    - `term` es la forma consultada en la frase (`Context.term`, D-020): de
      ella salen los lemas del léxico.
    - `lemma` es el de la entrada (`Entry.lemma`): sus sentidos son los que
      se buscan.
    - `pos` es la categoría del contexto (`Context.pos`), o `None` si spaCy no
      localizó la palabra (D-016).
    - `lang` elige el léxico. El idioma es un dato (§3.3.1), como en
      `DistractorRequest` y en los validadores (D-027).

    La partícula de R1 no viaja: en F1 un contexto con partícula no usa la
    definición del léxico, y eso lo decide el dominio sin preguntarle.
    """

    external_id: str
    term: str
    lemma: str
    pos: str | None
    lang: str


# `Protocol` y no `Callable`, al revés que el normalizador y con el criterio de
# D-016: un léxico tiene estado que inyectar (el directorio de datos y las
# consultas abiertas), así que el adaptador es una clase configurada al
# construirla.
class Lexicon(Protocol):
    """Toda fuente de definiciones implementa esto y nada más."""

    def facts(self, queries: list[LexiconQuery]) -> dict[str, LexiconFacts]:
        """Los hechos de cada consulta, por `external_id`.

        Un idioma para el que el adaptador no tiene léxico da `ValueError`:
        es un error de quien llama, no un contexto desconocido, igual que un
        idioma sin marcadores de negación en los validadores (D-027).
        """
        ...
