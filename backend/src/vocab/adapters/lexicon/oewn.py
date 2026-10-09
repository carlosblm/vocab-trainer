"""Léxico sobre Open English WordNet, edición `oewn:2025`, con `wn` (D-025).

Implementa `ports.lexicon.Lexicon`. Hace las dos búsquedas de la medición de
D-025 (`scripts/measure_definition_source.py`), que piden configuraciones
opuestas y por eso van en dos `Wordnet`:

- **Lemas de la forma consultada**, con `wn.morphy.Morphy` como lematizador:
  propone los lemas del léxico a los que llevan sus reglas de sufijos y sus
  excepciones, más la propia forma si es un lema. Si no propone ninguno, `wn`
  busca la forma tal cual entre todas las del léxico. Límite heredado: Morphy
  distingue mayúsculas al comparar con el léxico, así que `americans` no llega
  a `American`.
- **Sentidos del lema de la entrada**, sin lematizar y sin mirar formas no
  lemáticas (`search_all_forms=False`): `found` da los 3 sentidos de *found*
  como verbo, no los 18 que saldrían sumando los de *find*.

Toda comparación se hace en minúsculas. Categorías: NOUN → `n`, VERB → `v`,
ADJ → `a` y `s` (adjetivos y satélites), ADV → `r`; cualquier otra no tiene
equivalente.

La unidad de R1 no se busca. En F1, un contexto con partícula va a
`cloze_original` esté o no la unidad en el léxico, y eso lo decide el dominio.
La búsqueda volverá con la selección de sentido de F4.

Solo hay léxico para inglés: cualquier otro idioma da `ValueError`.

**`wn.config` es global.** `wn` guarda el directorio de datos en un objeto del
proceso, y cada consulta usa la base que indique en ese momento. El adaptador
lo fija al construirse; si otro código lo cambia después, sus consultas irán a
otra base.
"""

from pathlib import Path

import wn
from wn.constants import ADJ, ADJ_SAT, ADV, NOUN, VERB
from wn.morphy import Morphy

from vocab.domain.definition_policy import LexiconFacts, Sense
from vocab.ports.lexicon import LexiconQuery

# Una constante y no configuración: los recuentos de D-025 son de esta edición,
# y cambiarla exige volver a medir. `oewn:2025+` se descartó porque sus nombres
# propios suman sentidos a palabras comunes al comparar en minúsculas.
LEXICON = "oewn:2025"
# El único idioma de ese léxico.
LANG = "en"

# El adjetivo cubre también los satélites, que WordNet separa en otra pos.
WORDNET_POS: dict[str, tuple[str, ...]] = {
    "NOUN": (NOUN,),
    "VERB": (VERB,),
    "ADJ": (ADJ, ADJ_SAT),
    "ADV": (ADV,),
}

_UNSUPPORTED = LexiconFacts(pos_supported=False, term_lemmas=frozenset(), senses=())


class LexiconNotDownloaded(Exception):
    """El léxico no está en el directorio de datos. Su mensaje dice cómo
    descargarlo."""


class OewnLexicon:
    """El léxico `oewn:2025` del directorio de datos `data_dir`.

    Falla al construirse con `LexiconNotDownloaded` si el léxico no está
    descargado, no en la primera consulta. Comprueba que la base exista antes
    de abrirla: `wn` crearía una vacía en su lugar.
    """

    def __init__(self, data_dir: Path) -> None:
        directory = data_dir.expanduser()
        wn.config.data_directory = directory
        if not wn.config.database_path.is_file() or not wn.lexicons(lexicon=LEXICON):
            raise LexiconNotDownloaded(
                f"El léxico {LEXICON} no está descargado en {directory}. "
                f"Descárgalo, desde backend/, con: uv run python -m wn --dir "
                f"{directory} download {LEXICON}"
            )
        self._lemmatizing = wn.Wordnet(LEXICON)
        # Morphy se construye sobre el léxico para proponer solo lemas que
        # existen en él, así que se asigna después de crear el `Wordnet`.
        self._lemmatizing.lemmatizer = Morphy(self._lemmatizing)
        self._exact = wn.Wordnet(LEXICON, search_all_forms=False)

    def facts(self, queries: list[LexiconQuery]) -> dict[str, LexiconFacts]:
        """Ver `Lexicon.facts`. Comprueba los idiomas del lote antes de
        consultar nada."""
        other = next((query for query in queries if query.lang != LANG), None)
        if other is not None:
            raise ValueError(
                f"El léxico {LEXICON} solo es de inglés ({LANG!r}): la consulta "
                f"{other.external_id!r} está en {other.lang!r}."
            )
        return {query.external_id: self._facts(query) for query in queries}

    def _facts(self, query: LexiconQuery) -> LexiconFacts:
        pos = query.pos
        if pos is None or pos not in WORDNET_POS:
            return _UNSUPPORTED
        pos_tags = WORDNET_POS[pos]

        term = query.term.lower()
        term_lemmas = frozenset(
            word.lemma().lower()
            for tag in pos_tags
            for word in self._lemmatizing.words(term, tag)
        )
        return LexiconFacts(
            pos_supported=True,
            term_lemmas=term_lemmas,
            senses=self._senses(query.lemma.lower(), pos_tags),
        )

    def _senses(self, lemma: str, pos_tags: tuple[str, ...]) -> tuple[Sense, ...]:
        """Los sentidos de `lemma` en las pos de la categoría, en el orden del
        léxico y sin repetir."""
        found: dict[str, Sense] = {}
        for tag in pos_tags:
            for sense in self._exact.senses(lemma, tag):
                if sense.id not in found:
                    found[sense.id] = Sense(id=sense.id, gloss=_gloss(sense))
        return tuple(found.values())


def _gloss(sense: wn.Sense) -> str:
    """La definición del synset del sentido.

    `wn` la tipa como opcional, pero en `oewn:2025` todos los synsets tienen
    definición (comprobado en su base el 2026-10-07). Un sentido sin ella
    sería otra edición, y se avisa en vez de enseñar una cadena vacía.
    """
    definition = sense.synset().definition()
    if definition is None:
        raise ValueError(f"El sentido {sense.id} no tiene definición en {LEXICON}.")
    return definition
