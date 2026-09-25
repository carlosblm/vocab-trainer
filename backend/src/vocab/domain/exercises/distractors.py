"""Regla de distractores de la variante de elección de `cloze_original` (D-022).

Un distractor solo sirve si la gramática no lo delata: en «She _____ on the
maps» solo encaja un verbo en pasado, así que un sustantivo o un gerundio se
descartan sin conocer la palabra. Por eso los distractores comparten con la
respuesta la categoría y los rasgos morfológicos (`Context.pos` y
`Context.morph`), y salen solo de las palabras que el propio lector consultó.

Función pura: los candidatos y el azar entran por parámetro, y el resultado son
las opciones o `None`. Si no hay tres candidatos, no se relaja la gramática ni
se reduce el número de opciones: quien llama recurre a la variante de
escritura. En la exportación de septiembre de 2026 pasa en 13 de los 999
contextos de `study`, todos de clases cerradas o raras.
"""

import random
from collections.abc import Iterable

from vocab.domain.exercises.cloze_original_choice import OPTION_COUNT
from vocab.domain.models import Context, Entry, EntryStatus


def choose_options(
    entry: Entry,
    context: Context,
    candidates: Iterable[Entry],
    rng: random.Random,
) -> tuple[str, ...] | None:
    """Las opciones del ejercicio sobre `context`, en su orden, o `None` si
    no hay distractores suficientes (ver `eligible_forms`)."""
    forms = eligible_forms(entry, context, candidates)
    if len(forms) < OPTION_COUNT - 1:
        return None

    answer = context.term
    options = [answer, *rng.sample(forms, OPTION_COUNT - 1)]
    rng.shuffle(options)
    return tuple(_written_like(option, answer) for option in options)


def eligible_forms(
    entry: Entry, context: Context, candidates: Iterable[Entry]
) -> list[str]:
    """Las formas que pueden ser distractores de `context`, sin repetir y en el
    orden de los candidatos. Cuántas hay explica por qué un contexto se queda
    sin opciones.

    Un candidato vale si:

    - su entrada no es `noise`, es del mismo idioma y tiene otro lema: dos
      formas del mismo lema (`learned`, `learnt`) serían dos respuestas
      correctas;
    - su contexto tiene la misma categoría y los mismos rasgos que la
      respuesta;
    - su forma no repite, sin distinguir mayúsculas, la respuesta ni otro
      candidato.

    Una respuesta sin analizar (`pos = None`) no tiene forma que igualar, así
    que no admite ninguno.
    """
    if context.pos is None or context.morph is None:
        return []

    taken = {context.term.lower()}
    forms: list[str] = []
    for candidate in candidates:
        if (
            candidate.status is EntryStatus.NOISE
            or candidate.lang != entry.lang
            or candidate.lemma == entry.lemma
        ):
            continue
        for other in candidate.contexts:
            if (other.pos, other.morph) != (context.pos, context.morph):
                continue
            if other.term.lower() in taken:
                continue
            taken.add(other.term.lower())
            forms.append(other.term)
    return forms


def _written_like(form: str, model: str) -> str:
    """Escribe `form` como está escrita la respuesta en la frase.

    Si las opciones conservaran su propia escritura, la mayúscula delataría la
    respuesta: en la exportación de septiembre, 14 respuestas comunes van con
    mayúscula por abrir la frase o un titular. No se decide por la categoría
    PROPN porque no es fiable en ninguna de las dos direcciones: 12 PROPN son
    palabras comunes en minúscula (`geese`, `inn`). Las cuatro opciones siguen
    el patrón de la respuesta, así que por construcción no hay pista.
    """
    if model.isupper():
        return form.upper()
    if model != model.lower() and model == model.capitalize():
        return form.capitalize()
    # Minúscula, y también la escritura mixta (`PhD`): no se puede copiar,
    # así que todas las opciones, la respuesta incluida, van en minúscula.
    return form.lower()
