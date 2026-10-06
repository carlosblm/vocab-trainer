"""Caso de uso: tres distractores válidos para `mcq_definition`, o la
degradación (§7.3).

Genera, valida y, si algo falla, reintenta con el motivo del último fallo. Si
el proveedor no responde o se agotan los reintentos, devuelve `Degraded` con el
motivo. La plantilla determinista que sustituye a los distractores generados no
es de este módulo, y avisar tampoco: la función no imprime ni registra nada, y
quien la llama decide cómo mostrar el motivo.

Falta el juez semántico (J1–J3), que entra en este bucle en F4.
"""

from dataclasses import dataclass, replace

from vocab.domain.distractor_validation import Violation, validate_distractors
from vocab.ports.distractor_generator import (
    DistractorGenerator,
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedAnswer,
    MalformedOutput,
    RejectedDistractors,
)

# §7.3: «reintento con el motivo del fallo inyectado (máximo 2)». Con el intento
# inicial, el generador recibe como mucho tres llamadas.
MAX_RETRIES = 2


@dataclass(frozen=True)
class AcceptedAttempt:
    """Intento cuyos distractores pasaron la validación. Si está, es el último
    del historial."""


@dataclass(frozen=True)
class RejectedAttempt:
    """Intento cuyos distractores no pasaron la validación: cuáles eran, qué
    falló y en cuál.

    Los distractores se guardan además de las violaciones porque, hasta que
    llegue Langfuse en F2, el historial es la única evidencia de cómo falla el
    modelo. El hallazgo de §12.4 salió de leer esas salidas.
    """

    distractors: tuple[str, str, str]
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class MalformedAttempt:
    """Intento cuya salida no tenía la forma esperada, con el motivo que dio el
    adaptador."""

    reason: str


@dataclass(frozen=True)
class UnavailableAttempt:
    """Intento en que el proveedor no respondió, con el motivo de
    `GeneratorUnavailable`. Si está, es el último del historial."""

    reason: str


# Lo que pasó en cada intento: uno por llamada al generador. Se guardará con el
# ejercicio y dará la tasa de reintento de F2 (O3).
Attempt = AcceptedAttempt | RejectedAttempt | MalformedAttempt | UnavailableAttempt


@dataclass(frozen=True)
class Accepted:
    """Distractores aceptados, con todos los intentos que costaron."""

    distractors: GeneratedDistractors
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True)
class ProviderUnavailable:
    """El proveedor no respondió. `reason` es el de `GeneratorUnavailable`: un
    nombre de modelo mal escrito no debe degradar en silencio."""

    reason: str


@dataclass(frozen=True)
class RetriesExhausted:
    """Fallaron el intento inicial y los `MAX_RETRIES` reintentos. Por qué, lo
    dice el historial."""


@dataclass(frozen=True)
class Degraded:
    """No hay distractores generados: quien llama recurre a la plantilla.

    `cause` es una unión, como `retry` en el puerto: solo el proveedor caído
    lleva un `reason`, y no se puede construir uno sin el otro.

    `attempts` tiene tantos intentos como llamadas recibió el generador. Con
    `ProviderUnavailable`, el último es un `UnavailableAttempt` con el mismo
    `reason`.
    """

    cause: ProviderUnavailable | RetriesExhausted
    attempts: tuple[Attempt, ...]


def generate_distractors(
    request: DistractorRequest, generator: DistractorGenerator
) -> Accepted | Degraded:
    """Pide distractores hasta que pasen la validación, o degrada.

    - Distractores sin violaciones: `Accepted`.
    - Con violaciones: el siguiente intento lleva `RejectedDistractors` con
      esos distractores y esas violaciones.
    - `MalformedOutput`: el siguiente intento lleva `MalformedAnswer`.
    - `GeneratorUnavailable`: `Degraded` al momento, sin reintentar, también si
      ocurre en un reintento.
    - Tras `1 + MAX_RETRIES` intentos fallidos: `Degraded`.

    `request` es la petición original, sin `retry`. Cada reintento parte de
    ella con el motivo del último fallo y no acumula los anteriores.

    Un `ValueError` del validador (idioma sin lista, definición correcta
    vacía) no se captura: es un error de datos o de configuración, no un
    fallo del modelo, y tiene que verse.
    """
    attempts: list[Attempt] = []
    current = request
    for _ in range(1 + MAX_RETRIES):
        try:
            generated = generator.generate(current)
        except GeneratorUnavailable as error:
            attempts.append(UnavailableAttempt(error.reason))
            return Degraded(ProviderUnavailable(error.reason), tuple(attempts))
        except MalformedOutput as error:
            attempts.append(MalformedAttempt(error.reason))
            current = replace(request, retry=MalformedAnswer(error.reason))
            continue

        violations = validate_distractors(
            request.definition, generated.distractors, request.lang
        )
        if not violations:
            attempts.append(AcceptedAttempt())
            return Accepted(generated, tuple(attempts))
        attempts.append(RejectedAttempt(generated.distractors, violations))
        current = replace(
            request,
            retry=RejectedDistractors(generated.distractors, violations),
        )

    return Degraded(RetriesExhausted(), tuple(attempts))
