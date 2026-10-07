"""La tarea de distractores (A1) vista desde un LLM: plantilla, mensajes,
esquema de salida y lectura de la respuesta.

No sabe de ningún proveedor. Produce mensajes `role`/`content` y lee el texto
que devuelva el modelo; cómo se envían y cómo llega ese texto es asunto del
adaptador de cada proveedor (hoy, `ollama`).

**Ninguna frase que lea el modelo vive en Python.** Todas salen de un TOML por
(tarea, idioma, versión) dentro del paquete:
`prompts/distractors/<lang>/<version>.toml` (§3.3.4, regla 3). Eso incluye
cómo se explica un reintento: las frases de cada `ViolationCode` y los motivos
de una salida mal formada (D-028). Por eso el `reason` de `MalformedOutput`
está en el idioma del prompt: es texto para el modelo, que vuelve a leerlo en
el reintento.

Se lee con `importlib.resources`, no con una ruta relativa al proceso: el
archivo viaja dentro del paquete, también en la imagen, sin pasos extra (la
lección de D-021).

Las plantillas usan `string.Template` (`$term`) y no `str.format` (`{term}`),
porque el prompt muestra JSON y con `format` cada llave tendría que ir doble.
"""

import json
import tomllib
from collections import defaultdict
from importlib.resources import files
from string import Template
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
)

from vocab.domain.distractor_validation import ViolationCode
from vocab.ports.distractor_generator import (
    DistractorRequest,
    MalformedAnswer,
    MalformedOutput,
    RejectedDistractors,
)

TASK = "distractors"

# Los campos de la petición que puede citar una plantilla.
REQUEST_FIELDS = ("term", "lemma", "pos", "sentence", "definition")


class DistractorsOutput(BaseModel):
    """La salida que se exige al modelo: `{"distractors": [str, str, str]}`.

    Su esquema JSON va en la petición, para que el proveedor restrinja la
    generación (D-004), y con él se valida la respuesta. La tupla de tres da
    `minItems` y `maxItems` 3 en el esquema y es el tipo exacto del puerto.
    `extra="forbid"` añade `additionalProperties: false`.

    Que las cadenas no estén vacías no se pide aquí: es contenido, y lo
    comprueban los validadores del dominio (D-026).
    """

    model_config = ConfigDict(extra="forbid")

    distractors: tuple[str, str, str]


def _template(*allowed: str) -> AfterValidator:
    """Valida una plantilla al cargar el archivo: sintaxis correcta y ningún
    marcador fuera de `allowed`. Un `$defintion` mal escrito falla al
    construir el adaptador, no en la primera llamada."""

    def check(text: str) -> str:
        template = Template(text)
        if not template.is_valid():
            raise ValueError("marcador mal formado; un dólar literal se escribe $$")
        unknown = sorted(set(template.get_identifiers()) - set(allowed))
        if unknown:
            raise ValueError(
                f"marcadores desconocidos {unknown}; se admiten {list(allowed)}"
            )
        return text

    return AfterValidator(check)


class _RetryRejectedTemplates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: Annotated[str, _template(*REQUEST_FIELDS, "items")]
    kept: Annotated[str, _template("number", "distractor")]
    rejected: Annotated[str, _template("number", "distractor", "problems")]


class _RetryMalformedTemplates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: Annotated[str, _template(*REQUEST_FIELDS, "reason")]


class MalformedPhrases(BaseModel):
    """Por qué no se pudo leer la respuesta. Cada frase es el `reason` de una
    `MalformedOutput`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    invalid_json: Annotated[str, _template()]
    wrong_count: Annotated[str, _template("count")]
    wrong_shape: Annotated[str, _template()]
    truncated: Annotated[str, _template()]


class PromptFile(BaseModel):
    """El contenido de un archivo de prompt, validado al cargarlo.

    `extra="forbid"`: una clave mal escrita en el TOML es un error, no una
    plantilla que se ignora en silencio.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    system: Annotated[str, _template()]
    user: Annotated[str, _template(*REQUEST_FIELDS)]
    retry_rejected: _RetryRejectedTemplates
    retry_malformed: _RetryMalformedTemplates
    violations: dict[ViolationCode, Annotated[str, _template()]]
    malformed: MalformedPhrases

    @field_validator("violations")
    @classmethod
    def _every_code(cls, value: dict[ViolationCode, str]) -> dict[ViolationCode, str]:
        # Un código nuevo en el dominio sin su frase dejaría al modelo sin saber
        # qué falló. Se detecta al construir, no en el primer reintento.
        missing = sorted(set(ViolationCode) - value.keys())
        if missing:
            raise ValueError(f"falta la frase de {[str(code) for code in missing]}")
        return value


class DistractorPrompt:
    """Una versión del prompt en un idioma: construye los mensajes de una
    petición y lee la respuesta del modelo."""

    def __init__(self, file: PromptFile) -> None:
        self.file = file

    def messages(self, request: DistractorRequest) -> list[dict[str, str]]:
        """Sistema, usuario y, si la petición es un reintento, un segundo
        mensaje de usuario con el motivo.

        El reintento va aparte y no fundido con el primero: la tarea se lee
        igual en todos los intentos, y lo que cambia queda al final.
        """
        # De `REQUEST_FIELDS`, la misma lista con la que se validaron las
        # plantillas: un marcador admitido siempre tiene valor.
        fields = {name: getattr(request, name) for name in REQUEST_FIELDS}
        messages = [
            _message("system", self.file.system, {}),
            _message("user", self.file.user, fields),
        ]
        match request.retry:
            case RejectedDistractors() as rejected:
                items = self._items(rejected)
                messages.append(
                    _message(
                        "user",
                        self.file.retry_rejected.message,
                        {**fields, "items": items},
                    )
                )
            case MalformedAnswer(reason=reason):
                messages.append(
                    _message(
                        "user",
                        self.file.retry_malformed.message,
                        {**fields, "reason": reason},
                    )
                )
            case None:
                pass
        return messages

    def parse(self, content: str, *, truncated: bool) -> tuple[str, str, str]:
        """Los tres distractores de la respuesta, o `MalformedOutput` con la
        frase de `[malformed]` que explica por qué no se pudo leer.

        La respuesta cortada se mira primero: su JSON tampoco cerraría, pero
        «cortada» es la causa y lo que el modelo tiene que corregir. El número
        de distractores se mira antes que el resto del esquema por lo mismo:
        es el fallo más concreto.
        """
        phrases = self.file.malformed
        if truncated:
            raise MalformedOutput(phrases.truncated)
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise MalformedOutput(phrases.invalid_json) from error

        items = data.get("distractors") if isinstance(data, dict) else None
        if isinstance(items, list) and len(items) != 3:
            reason = Template(phrases.wrong_count).substitute(count=len(items))
            raise MalformedOutput(reason)
        try:
            return DistractorsOutput.model_validate(data).distractors
        except ValidationError as error:
            raise MalformedOutput(phrases.wrong_shape) from error

    def _items(self, retry: RejectedDistractors) -> str:
        """Los distractores anteriores, numerados desde 1, cada uno con las
        frases de sus violaciones o marcado para conservarlo.

        Los separadores (salto de línea entre distractores, `; ` entre frases)
        son formato y viven aquí; las palabras, en el archivo.
        """
        problems: defaultdict[int, list[str]] = defaultdict(list)
        for violation in retry.violations:
            phrase = self.file.violations[violation.code]
            problems[violation.distractor_index].append(phrase)

        templates = self.file.retry_rejected
        lines: list[str] = []
        for index, distractor in enumerate(retry.previous):
            number = index + 1
            if index in problems:
                line = Template(templates.rejected).substitute(
                    number=number,
                    distractor=distractor,
                    problems="; ".join(problems[index]),
                )
            else:
                line = Template(templates.kept).substitute(
                    number=number, distractor=distractor
                )
            lines.append(line)
        return "\n".join(lines)


def load_prompt(lang: str, version: str) -> DistractorPrompt:
    """La plantilla de distractores de `lang` en `version`.

    Un archivo que no existe o que no valida da `ValueError`. Lo llama el
    constructor del adaptador, así que una versión o un idioma sin archivo
    fallan al arrancar, no en la primera llamada.
    """
    resource = files("vocab.adapters.llm").joinpath(
        "prompts", TASK, lang, f"{version}.toml"
    )
    if not resource.is_file():
        raise ValueError(
            f"No hay prompt de {TASK} para el idioma {lang!r} en la versión "
            f"{version!r}: falta prompts/{TASK}/{lang}/{version}.toml en "
            "vocab.adapters.llm."
        )
    data = tomllib.loads(resource.read_text(encoding="utf-8"))
    return DistractorPrompt(PromptFile.model_validate(data))


def _message(role: str, template: str, fields: dict[str, str]) -> dict[str, str]:
    # `strip`: las cadenas multilínea del TOML empiezan y acaban con salto de
    # línea, que no aporta nada al modelo.
    return {"role": role, "content": Template(template).substitute(fields).strip()}
