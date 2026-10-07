"""Prueba la configuración de las tareas con IA (§3.3.4) leída del entorno.

Sin `.env`: cada test define sus variables y borra las de tarea que pudiera
haber cargado otro módulo (los de integración llaman a `load_dotenv`).
"""

import pytest
from pydantic import ValidationError

from vocab.config import LLMTaskSettings, Settings

TASK_PREFIX = "LLM_TASK__DISTRACTORS__"
TASK_FIELDS = ("PROVIDER", "MODEL", "PROMPT_VERSION", "THINK", "TEMPERATURE")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for field in TASK_FIELDS:
        monkeypatch.delenv(TASK_PREFIX + field, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test")
    return monkeypatch


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_task_is_read_from_nested_variables(env: pytest.MonkeyPatch) -> None:
    env.setenv(TASK_PREFIX + "PROVIDER", "ollama")
    env.setenv(TASK_PREFIX + "MODEL", "some-model:4b")
    env.setenv(TASK_PREFIX + "PROMPT_VERSION", "v1")

    assert _settings().llm_task.distractors == LLMTaskSettings(
        provider="ollama", model="some-model:4b", prompt_version="v1"
    )


def test_unset_think_and_temperature_stay_none(env: pytest.MonkeyPatch) -> None:
    env.setenv(TASK_PREFIX + "PROVIDER", "ollama")
    env.setenv(TASK_PREFIX + "MODEL", "some-model:4b")
    env.setenv(TASK_PREFIX + "PROMPT_VERSION", "v1")
    env.setenv(TASK_PREFIX + "THINK", "false")

    task = _settings().llm_task.distractors

    assert task is not None
    assert task.think is False
    assert task.temperature is None


def test_provider_other_than_ollama_fails_on_load(env: pytest.MonkeyPatch) -> None:
    env.setenv(TASK_PREFIX + "PROVIDER", "openai")
    env.setenv(TASK_PREFIX + "MODEL", "some-model")
    env.setenv(TASK_PREFIX + "PROMPT_VERSION", "v1")

    with pytest.raises(ValidationError, match="en F1 el único es 'ollama'"):
        _settings()


def test_commands_without_ai_load_without_task(env: pytest.MonkeyPatch) -> None:
    """`import` y `study` no usan la tarea: sin sus variables, la
    configuración carga igual."""
    assert _settings().llm_task.distractors is None
