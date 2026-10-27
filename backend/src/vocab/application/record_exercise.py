"""Caso de uso: guardar el ejercicio que se va a mostrar.

Una fila por ejercicio mostrado, con lo necesario para reconstruirlo y la
procedencia de sus distractores: modelo, plantilla o ninguna; la configuración
del generador si se le pidió algo, aunque degradara; el historial de intentos;
y la causa de la degradación si la hubo (§4.3, D-007).

Traduce el resultado de `next_exercise` al registro del puerto. El historial de
`generate_distractors` no puede cruzar hasta el adaptador, que no ve
`application/` (import-linter), así que viaja como `AttemptRecord`: aquí se
decide qué código se guarda para cada intento y para cada causa.
"""

from vocab.application.generate_distractors import (
    AcceptedAttempt,
    Attempt,
    MalformedAttempt,
    ProviderUnavailable,
    RejectedAttempt,
    RetriesExhausted,
    UnavailableAttempt,
)
from vocab.application.next_exercise import (
    ClozeExercise,
    DefinitionExercise,
    DegradationCause,
    ExerciseRejected,
    ModelDistractors,
    NextExercise,
    NoGenerator,
)
from vocab.domain.models import ContextKey
from vocab.ports.exercise_record import (
    AttemptOutcome,
    AttemptRecord,
    DegradationCode,
    DistractorSource,
    ExerciseRecord,
)
from vocab.ports.repository import ExerciseRepository


def record_exercise(repository: ExerciseRepository, item: NextExercise) -> int:
    """Guarda `item` y devuelve el id del ejercicio guardado.

    Confirmar es de quien abre la transacción: `study` guarda cada ejercicio
    en la suya, antes de mostrarlo.
    """
    user_id = repository.ensure_user()
    return repository.save_exercise(user_id, exercise_record(item))


def exercise_record(item: NextExercise) -> ExerciseRecord:
    """El registro de `item`, sin guardarlo."""
    context = ContextKey.of(item.entry, item.context)
    if isinstance(item, DefinitionExercise):
        source = item.source
        if isinstance(source, ModelDistractors):
            return ExerciseRecord(
                context=context,
                exercise=item.exercise,
                source=DistractorSource.MODEL,
                generator=source.generator,
                attempts=_attempts(source.attempts),
            )
        code, reason = _degradation(source.cause)
        return ExerciseRecord(
            context=context,
            exercise=item.exercise,
            source=DistractorSource.TEMPLATE,
            generator=source.generator,
            attempts=_attempts(source.attempts),
            degradation=code,
            degradation_reason=reason,
        )
    return _cloze_record(context, item)


def _cloze_record(context: ContextKey, item: ClozeExercise) -> ExerciseRecord:
    """Un `cloze_original` no tiene distractores de modelo ni de plantilla.
    Si viene de un contexto `eligible` que degradó, guarda lo que se intentó."""
    fallback = item.definition_fallback
    if fallback is None:
        return ExerciseRecord(
            context=context, exercise=item.exercise, source=DistractorSource.NONE
        )
    code, reason = _degradation(fallback.cause)
    return ExerciseRecord(
        context=context,
        exercise=item.exercise,
        source=DistractorSource.NONE,
        generator=fallback.generator,
        attempts=_attempts(fallback.attempts),
        degradation=code,
        degradation_reason=reason,
    )


def _attempts(attempts: tuple[Attempt, ...]) -> tuple[AttemptRecord, ...]:
    return tuple(_attempt(attempt) for attempt in attempts)


def _attempt(attempt: Attempt) -> AttemptRecord:
    match attempt:
        case AcceptedAttempt():
            return AttemptRecord(AttemptOutcome.ACCEPTED)
        case RejectedAttempt(distractors=distractors, violations=violations):
            return AttemptRecord(
                AttemptOutcome.REJECTED,
                distractors=distractors,
                violations=violations,
            )
        case MalformedAttempt(reason=reason):
            return AttemptRecord(AttemptOutcome.MALFORMED, reason=reason)
        case UnavailableAttempt(reason=reason):
            return AttemptRecord(AttemptOutcome.UNAVAILABLE, reason=reason)


def _degradation(cause: DegradationCause) -> tuple[DegradationCode, str | None]:
    """El código de la causa y su motivo, si lo tiene.

    De `ExerciseRejected` se guarda el motivo, no los distractores rechazados:
    el intento aceptado no los lleva en el historial.
    """
    match cause:
        case ProviderUnavailable(reason=reason):
            return DegradationCode.PROVIDER_UNAVAILABLE, reason
        case RetriesExhausted():
            return DegradationCode.RETRIES_EXHAUSTED, None
        case NoGenerator():
            return DegradationCode.NO_GENERATOR, None
        case ExerciseRejected(reason=reason):
            return DegradationCode.EXERCISE_REJECTED, reason
