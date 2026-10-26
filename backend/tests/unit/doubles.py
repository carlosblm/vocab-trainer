"""Dobles de prueba compartidos por los tests unitarios.

Un doble por puerto, en un solo sitio. Con una copia en cada test que lo
necesita, cada copia podría dejar de cumplir el contrato por su cuenta
(D-023).

Este módulo no importa nada de `vocab.adapters`.
"""

from collections import deque
from collections.abc import Iterable, Mapping

from vocab.domain.definition_policy import LexiconFacts
from vocab.ports.distractor_generator import (
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedOutput,
)
from vocab.ports.lexicon import LexiconQuery

# Lo que puede entregar el doble: un resultado o una de las dos excepciones del
# puerto. Ninguna otra, porque el puerto no promete otra.
Outcome = GeneratedDistractors | GeneratorUnavailable | MalformedOutput


class ScriptedDistractorGenerator:
    """Entrega un guion de resultados en orden y guarda las peticiones.

    Cada llamada consume el siguiente resultado: si es una excepción, la lanza.
    Una llamada de más es un error del test, no del proveedor, así que no lanza
    ninguna excepción del puerto que quien llama pudiera tratar como un fallo
    normal.
    """

    def __init__(self, outcomes: Iterable[Outcome]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[DistractorRequest] = []

    def generate(self, request: DistractorRequest) -> GeneratedDistractors:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError(
                f"Guion agotado: la llamada {len(self.requests)} no tiene resultado."
            )
        outcome = self._outcomes.popleft()
        if isinstance(outcome, GeneratedDistractors):
            return outcome
        raise outcome


# Lo que responde un léxico que no conoce ninguna categoría: los tests que no
# miran la definición lo usan como respuesta para todo.
NO_CATEGORY = LexiconFacts(
    pos_supported=False, term_lemmas=frozenset(), senses=(), lexicon="fake:1"
)


class FakeLexicon:
    """Responde con hechos preparados por forma consultada (`LexiconQuery.term`)
    y guarda cada lote recibido.

    Una forma sin hechos recibe `default`. Sin `default`, es un error del test,
    no un contexto desconocido: el doble no se inventa hechos.
    """

    def __init__(
        self,
        facts_by_term: Mapping[str, LexiconFacts] | None = None,
        default: LexiconFacts | None = None,
    ) -> None:
        self._facts_by_term = dict(facts_by_term or {})
        self._default = default
        self.batches: list[list[LexiconQuery]] = []

    def facts(self, queries: list[LexiconQuery]) -> dict[str, LexiconFacts]:
        self.batches.append(list(queries))
        result: dict[str, LexiconFacts] = {}
        for query in queries:
            facts = self._facts_by_term.get(query.term, self._default)
            if facts is None:
                raise AssertionError(f"El test no preparó hechos para {query.term!r}.")
            result[query.external_id] = facts
        return result
