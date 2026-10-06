"""Puerto de generación de distractores (A1, §5.2): tres definiciones falsas,
pero verosímiles, para `mcq_definition`.

Quien llama pide los distractores por este contrato y no sabe qué hay detrás: ni
el proveedor, ni el modelo, ni el prompt. Los resuelve el adaptador con la
configuración de la tarea (D-007), y por eso el modelo y la versión de prompt
vuelven en el resultado: cada ejercicio generado tiene que guardar qué
configuración lo produjo (§3.3.4, regla 4).

Sin nada de terceros. El esquema con el que el adaptador pida al proveedor la
salida estructurada (D-004) es asunto del adaptador; por esta frontera solo
cruzan dataclasses y las dos excepciones del puerto.
"""

from dataclasses import dataclass
from typing import Protocol

from vocab.domain.cleaning import CleanSentence


@dataclass(frozen=True)
class DistractorRequest:
    """Lo que necesita el generador para inventar tres definiciones falsas.

    - `term` es la forma consultada en la frase (`Context.term`, D-020) y
      `lemma`, el lema de la entrada. Viajan las dos: la frase muestra la
      forma, y la definición es del lema.
    - `pos` es la categoría de esa forma en su frase (`Context.pos`). Sirve
      para que los distractores tengan la categoría de la respuesta: si no la
      tienen, la gramática los delata (§5.2). No admite `None`: un contexto
      que spaCy no localizó (D-016) se queda fuera antes de llegar aquí.
    - `sentence` es la frase limpia, con el mismo tipo que exige el
      normalizador (D-016). La que vuelve de Postgres es `str` y hay que
      reetiquetarla al construir la petición.
    - `definition` es la definición correcta: los distractores tienen que ser
      falsos respecto a ella.
    - `lang` permite elegir el prompt, que se indexa por tarea, idioma y
      versión (§3.3.4, regla 3).
    - `feedback` es el motivo del fallo anterior, que se inyecta en el
      reintento (§7.3); `None` en el primer intento. Un reintento es la misma
      petición con otro `feedback`: `dataclasses.replace(request, feedback=…)`.
    """

    term: str
    lemma: str
    pos: str
    sentence: CleanSentence
    definition: str
    lang: str
    feedback: str | None = None


@dataclass(frozen=True)
class GeneratedDistractors:
    """Tres distractores y la configuración que los produjo.

    Una tupla de tres y no una lista: el número es parte del tipo. Un adaptador
    que reciba otra cantidad lanza `MalformedOutput` en vez de devolverla.

    `model` y `prompt_version` son los que resolvió el adaptador desde la
    configuración de la tarea. Nunca un nombre de modelo escrito en el código
    (D-007).
    """

    distractors: tuple[str, str, str]
    model: str
    prompt_version: str


class GeneratorUnavailable(Exception):
    """No se pudo hablar con el proveedor: conexión rechazada, tiempo agotado.

    También cuando el proveedor responde con un error (un 5xx, un modelo que
    no tiene cargado) en lugar de una salida: no hay nada que examinar. Nada
    de esto dice que la petición estuviera mal, así que su `reason` no sirve
    como `feedback`. Si se reintenta o se degrada a la plantilla (§7.3) lo
    decide quien llama.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MalformedOutput(Exception):
    """El proveedor respondió, pero la salida no tiene la forma esperada:
    exactamente tres cadenas de texto.

    Por ejemplo, la salida no se puede parsear, trae dos distractores o
    cuatro, o mezcla el razonamiento con el contenido (D-004). Es un fallo de
    forma, no de contenido, y su `reason` está escrito para que pueda volver
    como `feedback` en el reintento.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# `Protocol` y no `Callable`, al revés que el normalizador (D-016): un generador
# sí tiene estado que inyectar (proveedor, modelo, versión de prompt, tiempo de
# espera), así que el adaptador será una clase configurada al construirla.
class DistractorGenerator(Protocol):
    """Toda generación de distractores implementa esto y nada más."""

    def generate(self, request: DistractorRequest) -> GeneratedDistractors:
        """Devuelve tres distractores para la petición, o lanza una de las dos
        excepciones del puerto.

        - `GeneratorUnavailable`: no se obtuvo respuesta del proveedor.
        - `MalformedOutput`: hubo respuesta, pero no son tres cadenas.

        El adaptador traduce los errores de sus bibliotecas (HTTP, parseo) a
        estas dos excepciones: quien llama no conoce esas bibliotecas.

        Que la salida tenga forma no la hace buena. Validar el contenido no es
        responsabilidad del puerto ni de sus adaptadores, y tampoco si alguna
        cadena está vacía o se repite. Eso incluye que la respuesta correcta no
        se filtre en un distractor (D1), que coincida la categoría gramatical
        (D2), que no haya antónimos ni negaciones triviales (D7) y cualquier
        otra métrica de §6.1. Lo hacen los validadores de quien llama, que
        deciden si piden otro intento con `feedback`.
        """
        ...
