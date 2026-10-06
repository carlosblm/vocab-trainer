"""Dobles de prueba compartidos por los tests unitarios.

Un doble por puerto, en un solo sitio. Con una copia en cada test que lo
necesita, cada copia podría dejar de cumplir el contrato por su cuenta
(D-023).

Este módulo no importa nada de `vocab.adapters`.
"""

from collections import deque
from collections.abc import Iterable

from vocab.ports.distractor_generator import (
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedOutput,
)

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
