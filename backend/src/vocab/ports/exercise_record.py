"""Objetos de transferencia del registro de ejercicios: lo que se guarda de cada
ejercicio mostrado.

Por esta frontera cruzan los ejercicios del dominio tal cual, que son los que
se reconstruyen al leer, y la procedencia de sus distractores en tipos de este
módulo: el historial de intentos de la aplicación no puede llegar al adaptador
(import-linter), así que viaja traducido a `AttemptRecord`.

**Los valores guardados se escriben a mano**, como `DefinitionStatus`: el tipo
de ejercicio, la procedencia, la causa de la degradación y el resultado de cada
intento. Renombrar un miembro no debe cambiar lo guardado.
"""

from dataclasses import dataclass
from enum import Enum

from vocab.domain.distractor_validation import Violation
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import ContextKey
from vocab.ports.distractor_generator import GeneratorIdentity

# Un ejercicio del dominio, en cualquiera de sus variantes.
Exercise = McqDefinition | ClozeOriginalChoice | ClozeOriginal


class ExerciseKind(Enum):
    """El código de §2.3. Las dos variantes de `cloze_original` son el mismo
    tipo: las distingue el contenido, con opciones o sin ellas."""

    CLOZE_ORIGINAL = "cloze_original"
    MCQ_DEFINITION = "mcq_definition"


class DistractorSource(Enum):
    """De dónde salieron los distractores de un `mcq_definition`. Un
    `cloze_original` no los tiene de ninguno de los dos: sus opciones, si las
    hay, son palabras del propio vocabulario (D-022)."""

    MODEL = "model"
    TEMPLATE = "template"
    NONE = "none"


class DegradationCode(Enum):
    """Por qué los distractores no son del modelo (§7.3, D-036)."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RETRIES_EXHAUSTED = "retries_exhausted"
    NO_GENERATOR = "no_generator"
    EXERCISE_REJECTED = "exercise_rejected"


# Las causas en que sí hubo generador, y por tanto configuración que guardar.
WITH_GENERATOR = frozenset(DegradationCode) - {DegradationCode.NO_GENERATOR}


class AttemptOutcome(Enum):
    """Cómo acabó cada llamada al generador (D-028)."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MALFORMED = "malformed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AttemptRecord:
    """Un intento del historial: su resultado y lo que lo explica.

    - `REJECTED`: los distractores y sus violaciones.
    - `MALFORMED` y `UNAVAILABLE`: el motivo.
    - `ACCEPTED`: nada más; los distractores aceptados están en el ejercicio.
    """

    outcome: AttemptOutcome
    distractors: tuple[str, str, str] | None = None
    violations: tuple[Violation, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        rejected = self.outcome is AttemptOutcome.REJECTED
        with_reason = self.outcome in {
            AttemptOutcome.MALFORMED,
            AttemptOutcome.UNAVAILABLE,
        }
        if rejected != (self.distractors is not None and bool(self.violations)):
            raise ValueError(
                f"distractores y violaciones van juntos y solo al rechazar: {self!r}"
            )
        if with_reason != (self.reason is not None):
            raise ValueError(
                f"el motivo va solo con un intento mal formado o no disponible: "
                f"{self!r}"
            )


@dataclass(frozen=True)
class ExerciseRecord:
    """Un ejercicio mostrado y la procedencia de sus distractores.

    - `context` es el contexto del que salió; su entrada da el idioma.
    - `exercise` lleva todo lo necesario para reconstruirlo: la frase, la
      palabra, la respuesta y las opciones en su orden.
    - `generator` es la configuración del generador si se le pidió algo,
      aunque degradara; `None` si no se le pidió nada.
    - `attempts` es el historial de esas peticiones.
    - `degradation` es la causa si hubo degradación, y `degradation_reason`,
      su motivo si lo tiene.

    Las invariantes repiten lo que garantiza la aplicación al traducir su
    resultado, y se comprueban también al reconstruir el registro desde la
    base.
    """

    context: ContextKey
    exercise: Exercise
    source: DistractorSource
    generator: GeneratorIdentity | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    degradation: DegradationCode | None = None
    degradation_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is ExerciseKind.MCQ_DEFINITION) != (
            self.source is not DistractorSource.NONE
        ):
            raise ValueError(
                "solo un mcq_definition tiene distractores de modelo o plantilla"
            )
        if self.source is DistractorSource.MODEL and (
            self.generator is None or self.degradation is not None
        ):
            raise ValueError("los distractores del modelo van con su generador")
        if self.source is DistractorSource.TEMPLATE and self.degradation is None:
            raise ValueError("los distractores de la plantilla van con su causa")
        if self.degradation_reason is not None and self.degradation is None:
            raise ValueError("un motivo de degradación sin degradación")
        if self.degradation is not None and (
            (self.degradation in WITH_GENERATOR) != (self.generator is not None)
        ):
            raise ValueError(
                f"la causa {self.degradation.value} no cuadra con el generador"
            )

    @property
    def kind(self) -> ExerciseKind:
        if isinstance(self.exercise, McqDefinition):
            return ExerciseKind.MCQ_DEFINITION
        return ExerciseKind.CLOZE_ORIGINAL
