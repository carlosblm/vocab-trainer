"""Mide cómo cubre Open English WordNet los contextos de estudio, para elegir la
fuente de definiciones de `mcq_definition` (F1; D-008, «Pendiente en F1»).

No es código de producción. Lee la base configurada en una transacción de solo
lectura —Postgres rechaza cualquier escritura— y solo escribe en la salida
estándar.

**Población**: los contextos utilizables (`Context.is_usable`) de las entradas
`learning`, los mismos que usa `study`. Se leen con la lectura real del
repositorio, `list_learning_entries_with_usable_context`.

**Léxico**: `oewn:2025`, del directorio de datos de `wn` que indica
`WN_DATA_DIR`. Es una de las dos ediciones más recientes que ofrece `wn` 1.1.1,
las dos de 2025-12-31; la otra, `2025+`, añade nombres propios de Open English
Namenet.

**Búsquedas en el léxico.** Toda comparación se hace en minúsculas.

- *Categoría* de un contexto: `Context.pos` traducido a WordNet. NOUN → `n`,
  VERB → `v`, ADJ → `a` y `s` (adjetivos y satélites), ADV → `r`.
- *Lemas del léxico* de una forma: los lemas, en minúsculas, de las palabras que
  devuelve `Wordnet.words(forma.lower(), pos)` con `wn.morphy.Morphy` como
  lematizador, unidos para las pos de la categoría. Es la búsqueda con
  lematizador de `wn`: Morphy propone los lemas del léxico a los que llevan sus
  reglas de sufijos y sus excepciones, más la propia forma si es un lema; si no
  propone ninguno, se busca la forma tal cual entre todas las formas del
  léxico. La búsqueda compara también con la forma normalizada que guarda `wn`
  (sin mayúsculas ni diacríticos), así que `american` encuentra `American`.
  Límite: Morphy compara sus candidatos con el léxico distinguiendo mayúsculas,
  así que la flexión de un lema con mayúscula no llega a él (`americans` no
  encuentra `American`).
- *Sentidos* de un lema: los sentidos de las palabras cuyo lema es ese, sin
  lematizar y sin mirar las formas no lemáticas (`search_all_forms=False`).
  `found` cuenta los 3 sentidos de *found* como verbo, no los 18 que salen
  sumando los de *find*.

**Categorías.** Cada contexto cae en una sola: la primera que cumple, en este
orden.

a. `pos_unmapped`: `Context.pos` es `None` o no es NOUN, VERB, ADJ ni ADV.
b. `form_not_found`: `Context.term` no tiene ningún lema del léxico en su
   categoría.
c. `lemma_disagrees`: los lemas del léxico de `Context.term` no son
   exactamente `{Entry.lemma}`. `lemma_missing` si `Entry.lemma` no está entre
   ellos; `lemma_with_others` si está, acompañado de otros.
d. `monosemous`: `Entry.lemma` tiene exactamente un sentido en la categoría.
e. `polysemous`: tiene dos o más.

**Guarda R1**, aparte y sobre los mismos contextos: `detect_particles` de
`adapters/nlp/lexical_unit.py`, con `Context.term` y la frase limpia. Para cada
contexto marcado, la unidad es `Entry.lemma`, un espacio y la partícula, que es
como OEWN escribe las unidades multipalabra (`come up`); una unidad que el
léxico escribe con guion (`belly-up`) no se encuentra así. Se busca como
sentidos de un lema, en cualquier categoría, y se dan sus sentidos por pos.

**Reproducir**, desde `backend/`, con Postgres levantado y el `vocab.db` de
septiembre de 2026 importado:

    export WN_DATA_DIR=~/wn-data
    uv run python -m wn --dir "$WN_DATA_DIR" download oewn:2025
    uv run python scripts/measure_definition_source.py
"""

import os
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version

import wn
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# `wn.config` es la API documentada, pero `wn` no lo incluye en su `__all__` y
# mypy estricto rechaza la reexportación implícita. Es el mismo objeto.
from wn._config import config as wn_config
from wn.constants import ADJ, ADJ_SAT, ADV, NOUN, VERB
from wn.morphy import Morphy

from vocab.adapters.nlp.lexical_unit import detect_particles
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.config import get_settings
from vocab.domain.cleaning import CleanSentence
from vocab.domain.models import Context, Entry
from vocab.ports.normalizer import CleanedLookup

load_dotenv()

LEXICON = "oewn:2025"
SPACY_MODEL = "en_core_web_sm"

# El adjetivo cubre también los satélites, que WordNet separa en otra pos.
WORDNET_POS: dict[str, tuple[str, ...]] = {
    "NOUN": (NOUN,),
    "VERB": (VERB,),
    "ADJ": (ADJ, ADJ_SAT),
    "ADV": (ADV,),
}

POS_UNMAPPED = "pos_unmapped"
FORM_NOT_FOUND = "form_not_found"
LEMMA_DISAGREES = "lemma_disagrees"
MONOSEMOUS = "monosemous"
POLYSEMOUS = "polysemous"
CATEGORIES = (POS_UNMAPPED, FORM_NOT_FOUND, LEMMA_DISAGREES, MONOSEMOUS, POLYSEMOUS)

LEMMA_MISSING = "lemma_missing"
LEMMA_WITH_OTHERS = "lemma_with_others"


@dataclass(frozen=True)
class StudyContext:
    """Un contexto con su entrada: clasificarlo exige `Context.term` y
    `Entry.lemma` a la vez."""

    entry: Entry
    context: Context


@dataclass(frozen=True)
class Classification:
    category: str
    # Lemas del léxico de `Context.term`. Vacío si no se llegaron a buscar.
    lemmas: frozenset[str] = frozenset()


class Lexicon:
    """Las búsquedas de la medición sobre el léxico.

    Son dos `Wordnet` porque las dos búsquedas piden configuraciones opuestas:
    llevar una forma a sus lemas tiene que lematizar y mirar todas las formas;
    contar los sentidos de un lema no debe hacer ni lo uno ni lo otro.
    """

    def __init__(self, specifier: str) -> None:
        self._lemmatizing = wn.Wordnet(specifier)
        # Morphy se construye sobre el léxico para proponer solo lemas que
        # existen en él, así que se asigna después de crear el `Wordnet`.
        self._lemmatizing.lemmatizer = Morphy(self._lemmatizing)
        self._exact = wn.Wordnet(specifier, search_all_forms=False)

    @property
    def description(self) -> str:
        """El léxico que se ha cargado de verdad, no el que se pidió."""
        return ", ".join(
            f"{lexicon.id}:{lexicon.version} ({lexicon.label})"
            for lexicon in self._exact.lexicons()
        )

    def lemmas(self, form: str, pos_tags: tuple[str, ...]) -> frozenset[str]:
        return frozenset(
            word.lemma().lower()
            for pos in pos_tags
            for word in self._lemmatizing.words(form.lower(), pos)
        )

    def sense_count(self, lemma: str, pos_tags: tuple[str, ...]) -> int:
        return len(
            {sense.id for pos in pos_tags for sense in self._exact.senses(lemma, pos)}
        )

    def senses_by_pos(self, lemma: str) -> Counter[str]:
        return Counter(sense.word().pos for sense in self._exact.senses(lemma))


def read_study_contexts() -> list[StudyContext]:
    # Solo lectura impuesta por Postgres, no por convención: también rechaza
    # el usuario que `ensure_user` crearía en una base vacía.
    engine = create_engine(
        get_settings().database_url,
        execution_options={"postgresql_readonly": True},
    )
    try:
        with Session(engine) as session:
            repository = PostgresVocabularyRepository(session)
            entries = repository.list_learning_entries_with_usable_context(
                repository.ensure_user()
            )
    finally:
        engine.dispose()
    return [
        StudyContext(entry, context)
        for entry in entries
        for context in entry.usable_contexts
    ]


def classify(item: StudyContext, lexicon: Lexicon) -> Classification:
    """Primera categoría que cumple el contexto, en el orden del docstring."""
    pos = item.context.pos
    if pos is None or pos not in WORDNET_POS:
        return Classification(POS_UNMAPPED)
    pos_tags = WORDNET_POS[pos]

    lemmas = lexicon.lemmas(item.context.term, pos_tags)
    if not lemmas:
        return Classification(FORM_NOT_FOUND)

    lemma = item.entry.lemma.lower()
    if lemmas != {lemma}:
        return Classification(LEMMA_DISAGREES, lemmas)

    senses = lexicon.sense_count(lemma, pos_tags)
    # El lema acaba de salir del léxico en esta categoría: cero sentidos sería
    # un error de la medición, no un dato.
    assert senses > 0, f"{lemma!r} sin sentidos en {pos_tags}"
    return Classification(MONOSEMOUS if senses == 1 else POLYSEMOUS, lemmas)


def disagreement(item: StudyContext, classification: Classification) -> str:
    if item.entry.lemma.lower() in classification.lemmas:
        return LEMMA_WITH_OTHERS
    return LEMMA_MISSING


def detect_r1(items: list[StudyContext]) -> dict[str, str | None]:
    """La guarda tal cual, con la forma consultada en cada frase (D-020).

    La frase vuelve de Postgres como `str` y se reetiqueta a mano: ya pasó por
    la limpieza al importarse.
    """
    return detect_particles(
        [
            CleanedLookup(
                external_id=item.context.external_id,
                word=item.context.term,
                lang=item.entry.lang,
                clean_sentence=CleanSentence(item.context.clean_sentence),
            )
            for item in items
        ]
    )


def format_senses(senses: Counter[str]) -> str:
    if not senses:
        return "0"
    detail = ", ".join(f"{pos}={count}" for pos, count in sorted(senses.items()))
    return f"{senses.total()} ({detail})"


def main() -> None:
    # Obligatoria: sin ella `wn` usaría en silencio su directorio por defecto.
    wn_config.data_directory = os.environ["WN_DATA_DIR"]
    lexicon = Lexicon(LEXICON)

    items = read_study_contexts()
    print(f"Contextos utilizables de entradas learning: {len(items)}")

    classified = [(item, classify(item, lexicon)) for item in items]
    counts = Counter(classification.category for _, classification in classified)

    print("\nCategorías")
    for category in CATEGORIES:
        print(f"  {category}: {counts[category]}")
        if category == POS_UNMAPPED:
            by_pos = Counter(
                str(item.context.pos)
                for item, classification in classified
                if classification.category == POS_UNMAPPED
            )
            for pos, count in by_pos.most_common():
                print(f"    {pos}: {count}")
        if category == LEMMA_DISAGREES:
            by_kind = Counter(
                disagreement(item, classification)
                for item, classification in classified
                if classification.category == LEMMA_DISAGREES
            )
            for kind in (LEMMA_MISSING, LEMMA_WITH_OTHERS):
                print(f"    {kind}: {by_kind[kind]}")

    print(
        f"\n{LEMMA_DISAGREES}: tipo | term | Entry.lemma | lemas del léxico | "
        "frase limpia"
    )
    for item, classification in classified:
        if classification.category == LEMMA_DISAGREES:
            disagreement_row = (
                disagreement(item, classification),
                item.context.term,
                item.entry.lemma,
                ", ".join(sorted(classification.lemmas)),
                item.context.clean_sentence,
            )
            print("  " + " | ".join(disagreement_row))

    particles = detect_r1(items)
    marked = [item for item in items if particles[item.context.external_id]]
    print(f"\nR1 marca {len(marked)} contextos")
    print("  term | partícula | unidad | encontrada | sentidos | frase limpia")
    for item in marked:
        particle = particles[item.context.external_id]
        unit = f"{item.entry.lemma.lower()} {particle}"
        senses = lexicon.senses_by_pos(unit)
        unit_row = (
            item.context.term,
            str(particle),
            unit,
            "sí" if senses else "no",
            format_senses(senses),
            item.context.clean_sentence,
        )
        print("  " + " | ".join(unit_row))

    print("\nVersiones")
    print(f"  wn: {wn.__version__}")
    print(f"  léxico: {lexicon.description}")
    print(f"  {SPACY_MODEL}: {version(SPACY_MODEL)}")


if __name__ == "__main__":
    main()
