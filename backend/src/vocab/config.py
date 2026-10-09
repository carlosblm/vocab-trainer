"""Carga de la configuración de la aplicación desde variables de entorno."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMTaskSettings(BaseModel):
    """Configuración de una tarea con IA (§3.3.4, D-007).

    El modelo solo existe aquí, leído del entorno: ningún nombre de modelo en
    el código. `think` y `temperature` son opcionales; sin definir, el
    adaptador no los envía y rige el valor por defecto del proveedor.
    """

    provider: Literal["ollama"]
    model: str
    prompt_version: str
    think: bool | None = None
    temperature: float | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def _only_ollama(cls, value: object) -> object:
        # Con el `Literal` a secas, el error diría «Input should be 'ollama'»
        # sin decir por qué.
        if value != "ollama":
            raise ValueError(
                f"no hay adaptador para el proveedor {value!r}: en F1 el único "
                "es 'ollama'"
            )
        return value


class LLMTasks(BaseModel):
    """Una entrada por tarea. Sin definir, la tarea no está configurada y los
    comandos que no la usan (`import`, `study`) siguen funcionando."""

    distractors: LLMTaskSettings | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # `LLM_TASK__DISTRACTORS__MODEL` se lee como `llm_task.distractors.model`.
        env_nested_delimiter="__",
    )

    database_url: str
    log_level: str = "INFO"

    llm_task: LLMTasks = Field(default_factory=LLMTasks)

    wn_data_dir: Path | None = None
    """Directorio de datos de `wn` con el léxico de D-025. Opcional, como la
    tarea de distractores: `import` y `study` no lo usan.

    `wn` lee la misma variable al importarse, pero sin expandir `~` y solo del
    entorno del proceso, no del `.env`. Por eso el adaptador lo fija con
    `wn.config` a partir de este valor.
    """

    # Por proveedor, no por tarea: dos tareas con el mismo proveedor comparten
    # servidor (§8.2).
    ollama_base_url: str | None = None
    ollama_timeout_seconds: float = 150.0
    """Tiempo de espera de cada petición a Ollama, en segundos. Tiene que
    cubrir una llamada en frío, porque la carga del modelo cuenta dentro de la
    petición y el adaptador no reintenta un tiempo agotado.

    Medido el 2026-10-07 con `qwen3.5:4b`, Ollama 0.33.3, el prompt `v1` (358
    tokens de entrada), `think=false` y las 34 capas en GPU. Antes de cada
    llamada en frío, el modelo se descargó con `ollama stop`:

    | Llamada    | load_duration | total_duration |
    |------------|---------------|----------------|
    | Frío 1     | 41,902 s      | 71,201 s       |
    | Frío 2     | 5,643 s       | 6,579 s        |
    | Frío 3     | 5,398 s       | 6,170 s        |
    | Caliente 1 | 0,002 s       | 0,583 s        |
    | Caliente 2 | 0,001 s       | 0,518 s        |
    | Caliente 3 | 0,002 s       | 0,524 s        |

    Frío 1 fue la primera carga desde que arrancó Ollama, la que paga la
    primera petición tras cada arranque. Tardó diez veces más que las
    siguientes en cargar y también en generar ya cargado. La causa no está
    medida: puede ser la lectura del archivo desde disco, la inicialización de
    CUDA o las dos.

    150 s es algo más del doble de esa llamada, la peor medida, que es una sola
    muestra. El precio es que un Ollama colgado tarda eso en degradar.
    """


@lru_cache
def get_settings() -> Settings:
    return Settings()
