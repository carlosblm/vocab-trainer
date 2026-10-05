"""Muestra para medir la primera acepción como definición de `mcq_definition`
(F1).

Saca una muestra aleatoria de contextos y escribe, para cada uno, la glosa de la
primera acepción de su lema en Open English WordNet, en un CSV con una columna
vacía, `teaches_false_meaning`, para etiquetarla a mano. No es código de
producción: lee la base en una transacción de solo lectura y solo escribe el
CSV.

**Población**: los contextos que `measure_definition_source.py` clasifica como
`polysemous`, excluidos los que marca la guarda R1. La clasificación, el léxico
(`oewn:2025`), la lectura de la base y la guarda se importan de ese script; aquí
no se redefinen.

**Muestra**: 50 contextos, con `random.Random(20261005).sample` sobre la
población ordenada por `external_id`. Ordenar antes de muestrear hace que la
muestra no dependa del orden en que la base devuelve las filas, y `external_id`
es estable entre exportaciones (D-012), así que reimportar no la cambia.

**Primera acepción**: el primer sentido de `Entry.lemma` en su categoría, en el
orden del léxico. `wn` guarda los sentidos de cada entrada en el orden del XML,
o en el del atributo `n` si lo hay. Verificado con `bank` como sustantivo: sus
10 sentidos salen en el orden del documento, y el primero es «sloping land
(especially the slope beside a body of water)», como en Princeton WordNet 3.0.

El léxico ordena los sentidos dentro de una entrada, no entre entradas, y una
búsqueda de `wn` intercala los de varias entradas por su rango. Cuando el lema
casa con más de una —homógrafos numerados (`lead-n-1`, `lead-n-2`), variantes de
mayúsculas (`vat`, `VAT`) o, en ADJ, una entrada `a` y otra `s`—, se recorren
entrada por entrada: primero las que se escriben exactamente como `Entry.lemma`;
a igualdad, `a` antes que `s` y después el orden del léxico. Al ejecutarse se
imprime cuántos contextos de la muestra caen en cada caso.

**Columnas del CSV** (UTF-8): `external_id`, `term`, `lemma` (`Entry.lemma`),
`pos` (`Context.pos`), `sense_count` (los sentidos de todas las entradas: el
número que hizo `polysemous` al contexto), `first_sense_gloss`, `clean_sentence`
y `teaches_false_meaning`, vacía. El CSV lleva frases de los libros: va fuera del
repositorio, como el `vocab.db`. Si el archivo ya existe, el script no lo
sobrescribe, porque puede tener etiquetas hechas a mano.

**Reproducir**, desde `backend/`, con el léxico descargado como indica
`measure_definition_source.py`. Se ejecuta como módulo para que `scripts` sea
importable:

    export WN_DATA_DIR=~/wn-data
    uv run python -m scripts.sample_first_sense ~/vocab-data/first_sense_sample.csv
"""

import argparse
import csv
import os
import random
from pathlib import Path

import wn
from scripts.measure_definition_source import (
    LEXICON,
    POLYSEMOUS,
    WORDNET_POS,
    Lexicon,
    StudyContext,
    classify,
    detect_r1,
    read_study_contexts,
)
from wn import Word

# Por el mismo motivo que en `measure_definition_source.py`: `wn.config` no
# está en el `__all__` de `wn`.
from wn._config import config as wn_config

SEED = 20261005
SAMPLE_SIZE = 50
COLUMNS = (
    "external_id",
    "term",
    "lemma",
    "pos",
    "sense_count",
    "first_sense_gloss",
    "clean_sentence",
    "teaches_false_meaning",
)


def entries_in_order(
    exact: wn.Wordnet, lemma: str, pos_tags: tuple[str, ...]
) -> list[Word]:
    """Las entradas del lema en su categoría, en el orden en que se recorren
    sus sentidos.

    `sorted` es estable: dentro de cada grupo se conserva el orden de llegada,
    que es el de `pos_tags` (`a` antes que `s`) y, en cada pos, el del léxico.
    """
    words = [word for pos in pos_tags for word in exact.words(lemma, pos)]
    return sorted(words, key=lambda word: word.lemma() != lemma)


def pos_tags_of(item: StudyContext) -> tuple[str, ...]:
    # Un contexto `polysemous` ya pasó por la categoría a: su pos está mapeada.
    pos = item.context.pos
    assert pos is not None and pos in WORDNET_POS, f"pos sin mapear: {pos!r}"
    return WORDNET_POS[pos]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Muestra de la primera acepción para etiquetar a mano."
    )
    parser.add_argument("output", type=Path, help="Ruta del CSV, que no debe existir.")
    output: Path = parser.parse_args().output.expanduser()
    # Se comprueba antes de leer nada, para no fallar al final.
    if output.exists():
        raise SystemExit(
            f"{output} ya existe y puede tener etiquetas hechas a mano: "
            "no se sobrescribe."
        )

    wn_config.data_directory = os.environ["WN_DATA_DIR"]
    lexicon = Lexicon(LEXICON)
    # La misma configuración con la que `Lexicon` cuenta sentidos; se crea
    # aparte porque la suya es privada.
    exact = wn.Wordnet(LEXICON, search_all_forms=False)

    items = read_study_contexts()
    particles = detect_r1(items)
    population = sorted(
        (
            item
            for item in items
            if not particles[item.context.external_id]
            and classify(item, lexicon).category == POLYSEMOUS
        ),
        key=lambda item: item.context.external_id,
    )
    print(f"Población ({POLYSEMOUS} sin los marcados por R1): {len(population)}")

    sample = random.Random(SEED).sample(population, SAMPLE_SIZE)
    print(f"Muestra: {len(sample)} contextos, semilla {SEED}")

    rows: list[dict[str, str | int]] = []
    several_entries = mixed_adjective = 0
    for item in sample:
        pos_tags = pos_tags_of(item)
        lemma = item.entry.lemma.lower()
        words = entries_in_order(exact, lemma, pos_tags)
        senses = [sense for word in words for sense in word.senses()]
        sense_count = lexicon.sense_count(lemma, pos_tags)
        # Las entradas tienen que ser las que contó la clasificación; si no,
        # la muestra no hablaría de la población.
        assert len(senses) == sense_count, f"{lemma!r}: {len(senses)} ≠ {sense_count}"

        if len(words) > 1:
            several_entries += 1
        if len({word.pos for word in words}) > 1:
            mixed_adjective += 1

        rows.append(
            {
                "external_id": item.context.external_id,
                "term": item.context.term,
                "lemma": item.entry.lemma,
                "pos": str(item.context.pos),
                "sense_count": sense_count,
                "first_sense_gloss": senses[0].synset().definition() or "",
                "clean_sentence": item.context.clean_sentence,
                "teaches_false_meaning": "",
            }
        )

    print(f"  con el lema en varias entradas: {several_entries}")
    print(f"  de ellos, ADJ con sentidos de `a` y de `s`: {mixed_adjective}")

    with output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV: {output}")


if __name__ == "__main__":
    main()
