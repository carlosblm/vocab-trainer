"""El adaptador de Ollama de verdad, dentro del bucle de generación (§7.3).

Se salta si `OLLAMA_BASE_URL` no está definida o Ollama no responde, como los
tests que necesitan los vocab.db reales. Hace de raíz de composición mientras
el generador no esté conectado a la CLI: lee la configuración de la tarea,
construye el cliente y el adaptador, y llama a `generate_distractors`.

El modelo no es determinista: solo se comprueba la forma del resultado. Los
distractores y el historial de intentos se imprimen; `pytest -s` para verlos.
"""

import os
from collections.abc import Iterator

import httpx
import pytest
from dotenv import load_dotenv

from vocab.adapters.llm import OllamaDistractorGenerator
from vocab.application.generate_distractors import (
    MAX_RETRIES,
    Accepted,
    AcceptedAttempt,
    Attempt,
    Degraded,
    MalformedAttempt,
    RejectedAttempt,
    RetriesExhausted,
    UnavailableAttempt,
    generate_distractors,
)
from vocab.config import LLMTaskSettings, get_settings
from vocab.domain.cleaning import CleanSentence
from vocab.ports.distractor_generator import DistractorRequest

load_dotenv()


def _ollama_responds(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        httpx.get(f"{base_url}/api/version", timeout=2).raise_for_status()
    except httpx.HTTPError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _ollama_responds(os.environ.get("OLLAMA_BASE_URL")),
    reason="requiere Ollama: define OLLAMA_BASE_URL y arráncalo",
)

# Escritos a mano. `resilient` es la palabra de §12.4, donde el modelo dio
# negaciones: el caso que más fácilmente ejercita el reintento.
EXAMPLES = [
    DistractorRequest(
        term="craved",
        lemma="crave",
        pos="VERB",
        sentence=CleanSentence("All afternoon she craved something sweet."),
        definition="have an urgent desire for",
        lang="en",
    ),
    DistractorRequest(
        term="resilient",
        lemma="resilient",
        pos="ADJ",
        sentence=CleanSentence("The town proved resilient after the flood."),
        definition="able to recover quickly from misfortune",
        lang="en",
    ),
    DistractorRequest(
        term="reverie",
        lemma="reverie",
        pos="NOUN",
        sentence=CleanSentence("A knock at the door broke her reverie."),
        definition="a state of pleasant daydreaming",
        lang="en",
    ),
]


@pytest.fixture(scope="module")
def task() -> LLMTaskSettings:
    task = get_settings().llm_task.distractors
    assert task is not None, "define LLM_TASK__DISTRACTORS__* en .env"
    return task


@pytest.fixture(scope="module")
def generator(task: LLMTaskSettings) -> Iterator[OllamaDistractorGenerator]:
    settings = get_settings()
    assert settings.ollama_base_url is not None
    with httpx.Client(
        base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_seconds
    ) as client:
        yield OllamaDistractorGenerator(
            client,
            model=task.model,
            prompt_version=task.prompt_version,
            languages=("en",),
            think=task.think,
            temperature=task.temperature,
        )


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.lemma)
def test_real_model_gives_three_distractors_or_exhausts_retries(
    generator: OllamaDistractorGenerator,
    task: LLMTaskSettings,
    example: DistractorRequest,
) -> None:
    result = generate_distractors(example, generator)

    _print(example, result)
    assert 1 <= len(result.attempts) <= 1 + MAX_RETRIES
    match result:
        case Accepted(distractors=generated):
            assert len(generated.distractors) == 3
            assert all(isinstance(text, str) for text in generated.distractors)
            assert generated.model == task.model
            assert generated.prompt_version == task.prompt_version
            assert isinstance(result.attempts[-1], AcceptedAttempt)
        case Degraded(cause=cause):
            # Agotar los reintentos es un resultado posible de un modelo no
            # determinista. Que el proveedor no esté disponible, con Ollama
            # respondiendo, es un error de configuración.
            assert isinstance(cause, RetriesExhausted), cause


def _print(example: DistractorRequest, result: Accepted | Degraded) -> None:
    print(f"\n{example.term} ({example.pos}) · correcta: {example.definition}")
    for number, attempt in enumerate(result.attempts, start=1):
        print(f"  intento {number}: {_describe(attempt)}")
    if isinstance(result, Accepted):
        for distractor in result.distractors.distractors:
            print(f"    - {distractor}")
    else:
        print(f"  degradado: {result.cause}")


def _describe(attempt: Attempt) -> str:
    match attempt:
        case AcceptedAttempt():
            return "aceptado"
        case RejectedAttempt(distractors=distractors, violations=violations):
            found = ", ".join(
                f"{violation.code} en {violation.distractor_index + 1}"
                for violation in violations
            )
            return f"rechazado ({found}): {list(distractors)}"
        case MalformedAttempt(reason=reason):
            return f"mal formado: {reason}"
        case UnavailableAttempt(reason=reason):
            return f"no disponible: {reason}"
