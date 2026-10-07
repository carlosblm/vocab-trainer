"""Prueba el adaptador de Ollama sin Ollama: `httpx.MockTransport` responde en
su lugar y anota cada petición.

Las frases esperadas se leen de la plantilla real (`en`, `v1`), no se copian
aquí: lo que se prueba es que el adaptador use la frase que toca, no su
redacción.
"""

import json
from dataclasses import replace
from string import Template
from typing import Any

import httpx
import pytest

from vocab.adapters.llm.distractors import DistractorsOutput, load_prompt
from vocab.adapters.llm.ollama import (
    TRANSPORT_RETRY_DELAY_SECONDS,
    OllamaDistractorGenerator,
)
from vocab.domain.cleaning import CleanSentence
from vocab.domain.distractor_validation import Violation, ViolationCode
from vocab.ports.distractor_generator import (
    DistractorGenerator,
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
    MalformedAnswer,
    MalformedOutput,
    RejectedDistractors,
)

BASE_URL = "http://ollama.test:11434"
CHAT_URL = f"{BASE_URL}/api/chat"
# Un nombre cualquiera: el adaptador lo recibe por parámetro, como en la raíz
# de composición.
MODEL = "some-model:4b"
PROMPT = load_prompt("en", "v1").file

REQUEST = DistractorRequest(
    term="craved",
    lemma="crave",
    pos="VERB",
    sentence=CleanSentence("All afternoon she craved something sweet."),
    definition="have an urgent desire for",
    lang="en",
)
DISTRACTORS = ("refuse to eat", "cook slowly over a low heat", "speak quietly")


def _chat(content: str, done_reason: str = "stop") -> httpx.Response:
    """Una respuesta de `/api/chat` con lo que el adaptador lee y algo que
    ignora."""
    return httpx.Response(
        200,
        json={
            "model": MODEL,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": done_reason,
            "total_duration": 1_500_000_000,
        },
    )


def _distractors(*items: str) -> httpx.Response:
    return _chat(json.dumps({"distractors": list(items)}))


class FakeOllama:
    """Entrega respuestas en orden, o lanza la excepción de httpx que toque,
    y guarda cada petición recibida."""

    def __init__(self, *outcomes: httpx.Response | type[httpx.TransportError]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, httpx.Response):
            return outcome
        raise outcome("simulado", request=request)

    def bodies(self) -> list[dict[str, Any]]:
        """Los cuerpos enviados, como JSON sin tipos: `Any` es su tipo real."""
        return [json.loads(request.content) for request in self.requests]


def _generator(
    fake: FakeOllama,
    sleeps: list[float] | None = None,
    *,
    think: bool | None = None,
    temperature: float | None = None,
) -> OllamaDistractorGenerator:
    """El adaptador sobre `fake`. Las esperas se anotan en `sleeps` en vez de
    dormir."""
    client = httpx.Client(
        transport=httpx.MockTransport(fake), base_url=BASE_URL, timeout=30
    )
    record = sleeps if sleeps is not None else []
    return OllamaDistractorGenerator(
        client,
        model=MODEL,
        prompt_version="v1",
        languages=("en",),
        think=think,
        temperature=temperature,
        sleep=record.append,
    )


def test_success_returns_distractors_with_the_task_configuration() -> None:
    fake = FakeOllama(_distractors(*DISTRACTORS))
    # Asignación tipada: mypy comprueba que el adaptador cumple el puerto.
    generator: DistractorGenerator = _generator(fake)

    result = generator.generate(REQUEST)

    assert result == GeneratedDistractors(
        distractors=DISTRACTORS, model=MODEL, prompt_version="v1"
    )
    assert len(fake.requests) == 1


def test_request_body_uses_native_endpoint_model_think_and_schema() -> None:
    fake = FakeOllama(_distractors(*DISTRACTORS))

    _generator(fake, think=False, temperature=0.2).generate(REQUEST)

    (request,) = fake.requests
    assert request.method == "POST"
    assert str(request.url) == CHAT_URL
    body = fake.bodies()[0]
    assert body["model"] == MODEL
    assert body["stream"] is False
    assert body["think"] is False
    assert body["options"] == {"temperature": 0.2}
    assert body["format"] == DistractorsOutput.model_json_schema()
    assert [message["role"] for message in body["messages"]] == ["system", "user"]


def test_unset_think_and_temperature_are_not_sent() -> None:
    fake = FakeOllama(_distractors(*DISTRACTORS))

    _generator(fake).generate(REQUEST)

    body = fake.bodies()[0]
    assert "think" not in body
    assert "options" not in body


def test_invalid_json_is_malformed() -> None:
    fake = FakeOllama(_chat("Sure! Here are three definitions: {"))

    with pytest.raises(MalformedOutput) as error:
        _generator(fake).generate(REQUEST)

    assert error.value.reason == PROMPT.malformed.invalid_json


@pytest.mark.parametrize("count", [2, 4])
def test_wrong_number_of_distractors_is_malformed(count: int) -> None:
    fake = FakeOllama(_distractors(*[f"definition {n}" for n in range(count)]))

    with pytest.raises(MalformedOutput) as error:
        _generator(fake).generate(REQUEST)

    expected = Template(PROMPT.malformed.wrong_count).substitute(count=count)
    assert error.value.reason == expected


def test_truncated_answer_is_malformed_even_if_it_parses() -> None:
    """`done_reason` manda: la causa es el corte, aunque el JSON cerrara."""
    fake = FakeOllama(
        _chat(json.dumps({"distractors": list(DISTRACTORS)}), done_reason="length")
    )

    with pytest.raises(MalformedOutput) as error:
        _generator(fake).generate(REQUEST)

    assert error.value.reason == PROMPT.malformed.truncated


def test_not_found_is_unavailable_at_once_with_url_model_and_detail() -> None:
    fake = FakeOllama(httpx.Response(404, json={"error": f'model "{MODEL}" not found'}))
    sleeps: list[float] = []

    with pytest.raises(GeneratorUnavailable) as error:
        _generator(fake, sleeps).generate(REQUEST)

    assert len(fake.requests) == 1
    assert sleeps == []
    assert CHAT_URL in error.value.reason
    assert MODEL in error.value.reason
    assert "404" in error.value.reason
    assert "not found" in error.value.reason


def test_server_error_then_success_retries_once_after_a_short_wait() -> None:
    fake = FakeOllama(
        httpx.Response(500, json={"error": "llama runner process has terminated"}),
        _distractors(*DISTRACTORS),
    )
    sleeps: list[float] = []

    result = _generator(fake, sleeps).generate(REQUEST)

    assert result.distractors == DISTRACTORS
    assert len(fake.requests) == 2
    assert sleeps == [TRANSPORT_RETRY_DELAY_SECONDS]


def test_server_error_twice_is_unavailable() -> None:
    fake = FakeOllama(httpx.Response(503), httpx.Response(503))
    sleeps: list[float] = []

    with pytest.raises(GeneratorUnavailable) as error:
        _generator(fake, sleeps).generate(REQUEST)

    assert len(fake.requests) == 2
    assert sleeps == [TRANSPORT_RETRY_DELAY_SECONDS]
    assert "503" in error.value.reason
    assert CHAT_URL in error.value.reason
    assert MODEL in error.value.reason


def test_timeout_is_unavailable_at_once_without_retry() -> None:
    """El tiempo de espera ya cubre la carga en frío: si se agota, Ollama está
    colgado. El segundo resultado del guion sobra a propósito; si se pidiera,
    el adaptador habría reintentado."""
    fake = FakeOllama(httpx.ReadTimeout, _distractors(*DISTRACTORS))
    sleeps: list[float] = []

    with pytest.raises(GeneratorUnavailable) as error:
        _generator(fake, sleeps).generate(REQUEST)

    assert len(fake.requests) == 1
    assert sleeps == []
    assert CHAT_URL in error.value.reason
    assert MODEL in error.value.reason
    assert "30 s" in error.value.reason


def test_connection_refused_is_unavailable_without_retry() -> None:
    fake = FakeOllama(httpx.ConnectError)
    sleeps: list[float] = []

    with pytest.raises(GeneratorUnavailable) as error:
        _generator(fake, sleeps).generate(REQUEST)

    assert len(fake.requests) == 1
    assert sleeps == []
    assert CHAT_URL in error.value.reason
    assert MODEL in error.value.reason


def test_success_status_without_chat_message_is_unavailable() -> None:
    """Un 200 que no es de `/api/chat` (otro servicio en esa URL) no se
    arregla repitiendo."""
    fake = FakeOllama(httpx.Response(200, json={"status": "ok"}))

    with pytest.raises(GeneratorUnavailable) as error:
        _generator(fake).generate(REQUEST)

    assert len(fake.requests) == 1
    assert "message.content" in error.value.reason


def test_retry_with_rejected_distractors_lists_them_with_each_violation() -> None:
    previous = ("refuse to eat", "not want anything", "refuse to eat")
    violations = (
        Violation(ViolationCode.DUPLICATE, 2),
        Violation(ViolationCode.NEGATION, 1),
    )
    retry = replace(REQUEST, retry=RejectedDistractors(previous, violations))
    fake = FakeOllama(_distractors(*DISTRACTORS))

    _generator(fake).generate(retry)

    messages = fake.bodies()[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "user"]
    last = messages[-1]["content"]
    for distractor in previous:
        assert distractor in last
    assert PROMPT.violations[ViolationCode.DUPLICATE] in last
    assert PROMPT.violations[ViolationCode.NEGATION] in last
    assert PROMPT.violations[ViolationCode.EMPTY] not in last


def test_retry_with_malformed_answer_carries_the_reason() -> None:
    reason = PROMPT.malformed.truncated
    retry = replace(REQUEST, retry=MalformedAnswer(reason))
    fake = FakeOllama(_distractors(*DISTRACTORS))

    _generator(fake).generate(retry)

    messages = fake.bodies()[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert reason in messages[-1]["content"]


@pytest.mark.parametrize(
    ("languages", "version"), [(("en",), "v999"), (("en", "xx"), "v1")]
)
def test_missing_prompt_fails_when_building_the_adapter(
    languages: tuple[str, ...], version: str
) -> None:
    fake = FakeOllama()
    client = httpx.Client(transport=httpx.MockTransport(fake), base_url=BASE_URL)

    with pytest.raises(ValueError, match="No hay prompt"):
        OllamaDistractorGenerator(
            client, model=MODEL, prompt_version=version, languages=languages
        )

    assert fake.requests == []


def test_language_not_loaded_is_a_value_error_without_calling_ollama() -> None:
    fake = FakeOllama()

    with pytest.raises(ValueError, match="'es'"):
        _generator(fake).generate(replace(REQUEST, lang="es"))

    assert fake.requests == []
