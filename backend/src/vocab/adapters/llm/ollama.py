"""Adaptador de Ollama para `DistractorGenerator` (A1), con el endpoint nativo
`/api/chat`.

Implementa `ports.distractor_generator.DistractorGenerator`. Los mensajes, el
esquema de salida y la lectura de la respuesta son de la tarea
(`distractors`). Aquí está lo que es de Ollama: el cuerpo de la petición, los
errores de transporte y el sobre de la respuesta.

Nunca `/v1/`: no propaga `think` y, con Qwen3, vuelca el razonamiento dentro
de `content` con un 200 (D-004). Por eso, además del código HTTP, se valida
`message.content`.

Cómo acaba cada caso:

- Respuesta 2xx con tres cadenas en `message.content`: `GeneratedDistractors`.
- Respuesta 2xx con `content` que no es JSON, sin tres distractores, o
  cortada (`done_reason` = `length`): `MalformedOutput`. El modelo respondió
  mal y otro intento puede salir bien, así que lo decide el bucle.
- 5xx: un único reintento tras una espera corta, porque un error del
  servidor puede no repetirse (D-028). Si vuelve a fallar,
  `GeneratorUnavailable`.
- Tiempo agotado: `GeneratorUnavailable` al momento, sin reintento.
- Conexión rechazada (Ollama apagado), 4xx (modelo inexistente, petición mal
  formada) o un 2xx que no es una respuesta de `/api/chat`:
  `GeneratorUnavailable` al momento. Repetir no lo arregla.

El `reason` de `GeneratorUnavailable` lleva la URL y el modelo: es lo que
necesita quien lea el aviso de degradación para arreglarlo.

**La política de transporte es de este adaptador y supone un Ollama local**,
en la misma máquina. El tiempo de espera se midió para cubrir la carga del
modelo en frío con margen (`Settings.ollama_timeout_seconds`). Si aun así se
agota, Ollama está colgado, y reintentar solo duplicaría la espera antes de
degradar. Un adaptador de API decidirá su propia política con sus propias
mediciones: red, límites de peticiones y latencias que aquí no existen.
"""

import time
from collections.abc import Callable, Iterable

import httpx
from pydantic import BaseModel, ValidationError

from vocab.adapters.llm.distractors import (
    DistractorPrompt,
    DistractorsOutput,
    load_prompt,
)
from vocab.ports.distractor_generator import (
    DistractorRequest,
    GeneratedDistractors,
    GeneratorUnavailable,
)

CHAT_PATH = "/api/chat"

# El intento y un único reintento, solo para 5xx.
TRANSPORT_ATTEMPTS = 2
# Corta: solo da margen a que el servidor se recupere. Esperar una carga no le
# corresponde; eso lo cubre el tiempo de espera de cada petición, que se
# configura en el cliente.
TRANSPORT_RETRY_DELAY_SECONDS = 1.0

# Se calcula una vez: es el mismo en todas las peticiones.
OUTPUT_SCHEMA = DistractorsOutput.model_json_schema()

# Lo que cabe del error de Ollama en un `reason`.
DETAIL_LIMIT = 200


class _ChatMessage(BaseModel):
    content: str


class _ChatResponse(BaseModel):
    """Lo que se lee de una respuesta de `/api/chat`. El resto (`thinking`,
    duraciones, recuentos de tokens) se ignora."""

    message: _ChatMessage
    done_reason: str | None = None


class OllamaDistractorGenerator:
    """Genera distractores con un modelo servido por Ollama.

    - `client` llega configurado con la URL base y el tiempo de espera de
      Ollama. Lo crea y lo cierra quien construye el adaptador, como la
      sesión de Postgres, y es lo que permite probarlo con
      `httpx.MockTransport` y sin red.
    - `model`, `prompt_version`, `think` y `temperature` son la configuración
      de la tarea (D-007). Con `think` o `temperature` a `None`, el campo no
      se envía y rige el valor por defecto de Ollama y del modelo.
    - `languages` son los idiomas en que se va a pedir. Sus plantillas se
      cargan aquí, así que un idioma o una versión sin archivo fallan al
      construir, no en la primera llamada.
    - `sleep` es la espera antes del reintento por 5xx; los tests la
      sustituyen para no esperar.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        model: str,
        prompt_version: str,
        languages: Iterable[str],
        think: bool | None = None,
        temperature: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._model = model
        self._prompt_version = prompt_version
        self._think = think
        self._temperature = temperature
        self._sleep = sleep
        self._prompts = {lang: load_prompt(lang, prompt_version) for lang in languages}
        if not self._prompts:
            raise ValueError("Hace falta al menos un idioma.")

    def generate(self, request: DistractorRequest) -> GeneratedDistractors:
        """Ver `DistractorGenerator.generate`.

        Un idioma que no se cargó al construir da `ValueError`: es un error de
        configuración, no un fallo del proveedor, y el bucle no lo captura,
        como el del validador (D-028).
        """
        prompt = self._prompt(request.lang)
        response = self._send(self._body(prompt, request))
        chat = self._chat(response)
        distractors = prompt.parse(
            chat.message.content, truncated=chat.done_reason == "length"
        )
        return GeneratedDistractors(
            distractors=distractors,
            model=self._model,
            prompt_version=self._prompt_version,
        )

    def _prompt(self, lang: str) -> DistractorPrompt:
        prompt = self._prompts.get(lang)
        if prompt is None:
            raise ValueError(
                f"El generador no cargó prompt para el idioma {lang!r}; "
                f"cargó {sorted(self._prompts)}."
            )
        return prompt

    def _body(
        self, prompt: DistractorPrompt, request: DistractorRequest
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self._model,
            "messages": prompt.messages(request),
            "stream": False,
            "format": OUTPUT_SCHEMA,
        }
        if self._think is not None:
            body["think"] = self._think
        if self._temperature is not None:
            body["options"] = {"temperature": self._temperature}
        return body

    def _send(self, body: dict[str, object]) -> httpx.Response:
        """La respuesta 2xx, con un reintento para 5xx."""
        failure = ""
        for attempt in range(TRANSPORT_ATTEMPTS):
            if attempt:
                self._sleep(TRANSPORT_RETRY_DELAY_SECONDS)
            outcome = self._attempt(body)
            if isinstance(outcome, httpx.Response):
                return outcome
            failure = outcome
        raise GeneratorUnavailable(f"{failure}, también al reintentar")

    def _attempt(self, body: dict[str, object]) -> httpx.Response | str:
        """Una petición: la respuesta 2xx, o el motivo de un fallo que admite
        reintento. Un fallo que no lo admite lanza `GeneratorUnavailable`."""
        request = self._client.build_request("POST", CHAT_PATH, json=body)
        try:
            response = self._client.send(request)
        except httpx.TimeoutException as error:
            # Sin reintento: ver «La política de transporte» en el módulo. Con
            # `stream: false` Ollama no envía nada hasta terminar, así que el
            # límite que cuenta es el de lectura.
            limit = self._client.timeout.read
            seconds = f" ({limit:g} s)" if limit is not None else ""
            reason = self._reason(request, f"tiempo de espera agotado{seconds}")
            raise GeneratorUnavailable(reason) from error
        except httpx.RequestError as error:
            reason = self._reason(request, f"no se pudo conectar ({error})")
            raise GeneratorUnavailable(reason) from error

        if response.is_success:
            return response
        failure = self._reason(
            request, f"respondió {response.status_code}: {_detail(response)}"
        )
        if response.is_server_error:
            return failure
        raise GeneratorUnavailable(failure)

    def _chat(self, response: httpx.Response) -> _ChatResponse:
        """El sobre de la respuesta. Si no tiene `message.content`, quien
        respondió no es `/api/chat` de Ollama, y otro intento no lo cambia."""
        try:
            return _ChatResponse.model_validate_json(response.content)
        except ValidationError as error:
            reason = self._reason(
                response.request,
                "la respuesta no tiene la forma de /api/chat (falta message.content)",
            )
            raise GeneratorUnavailable(reason) from error

    def _reason(self, request: httpx.Request, what: str) -> str:
        return f"Ollama en {request.url} con el modelo {self._model!r}: {what}"


def _detail(response: httpx.Response) -> str:
    """El campo `error` con el que responde Ollama a un fallo (`model "x" not
    found`), o el cuerpo tal cual si no lo trae, recortado."""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        error = None
    text = error if isinstance(error, str) else response.text
    return text.strip()[:DETAIL_LIMIT] or response.reason_phrase
