"""Caso de uso: importar vocabulario desde una fuente.

Además de entradas y contextos, decide al importar qué definición puede
enseñar cada contexto y la guarda con él (D-033): `study` lee la decisión de
la base y no carga ni spaCy ni el léxico.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from vocab.domain.cleaning import CleanSentence, clean_sentence, is_truncated
from vocab.domain.definition_policy import DefinitionDecision, decide_definition
from vocab.domain.models import Context, Entry
from vocab.domain.noise import LookedUpWord
from vocab.ports.importer import RawLookup, VocabularyImporter
from vocab.ports.lexicon import Lexicon, LexiconQuery
from vocab.ports.normalizer import CleanedLookup, NormalizedWord, Normalizer
from vocab.ports.repository import ImportRepository, ImportStats


@dataclass(frozen=True)
class _AnalyzedLookup:
    """Una consulta con todo lo que se sabe de ella: como llegó de la fuente,
    su frase ya limpia y el análisis del normalizador.

    Las propiedades dan nombre propio a lo que define una entrada —el término
    consultado, su idioma, cuándo se consultó—, para que agrupar y decidir el
    estado no dependan de en cuál de las tres piezas vive cada dato.
    """

    lookup: RawLookup
    clean_sentence: CleanSentence
    analysis: NormalizedWord

    @property
    def external_id(self) -> str:
        return self.lookup.external_id

    @property
    def term(self) -> str:
        return self.lookup.word

    @property
    def lang(self) -> str:
        return self.lookup.lang

    @property
    def looked_up_at(self) -> datetime:
        return self.lookup.looked_up_at

    @property
    def identity(self) -> tuple[str, str]:
        return (self.analysis.lemma, self.lang)


def import_vocabulary(
    importer: VocabularyImporter,
    repository: ImportRepository,
    normalizer: Normalizer,
    lexicon: Lexicon,
    filename: str,
) -> ImportStats:
    user_id = repository.ensure_user()
    source_id = repository.register_source(
        user_id=user_id,
        kind=importer.kind,
        filename=filename,
        checksum=importer.checksum(),
    )
    entries = _build_entries(importer.read(), normalizer, lexicon)
    return repository.upsert_entries(user_id, source_id, entries)


def _build_entries(
    lookups: Iterable[RawLookup], normalizer: Normalizer, lexicon: Lexicon
) -> list[Entry]:
    """Limpia, normaliza, decide la definición y agrupa las consultas en
    entradas.

    El orden importa: la limpieza va antes que la normalización porque el
    segmentador se atraganta con las notas al pie; la definición va después,
    porque necesita el lema, la categoría y la partícula; y la agrupación va al
    final porque la identidad de una entrada es su lema.

    El normalizador recibe un tipo reducido y devuelve los resultados en
    cualquier orden, así que se indexan por `external_id` para recomponer cada
    consulta con lo que no le hemos dado: la frase cruda, el libro y la fecha.
    """
    raw_by_id = {lookup.external_id: lookup for lookup in lookups}
    cleaned_lookups = [
        CleanedLookup(
            external_id=lookup.external_id,
            word=lookup.word,
            lang=lookup.lang,
            clean_sentence=clean_sentence(lookup.sentence),
        )
        for lookup in raw_by_id.values()
    ]
    analysis_by_id = {
        analysis.external_id: analysis for analysis in normalizer(cleaned_lookups)
    }
    analyzed = [
        _AnalyzedLookup(
            lookup=raw_by_id[cleaned.external_id],
            clean_sentence=cleaned.clean_sentence,
            analysis=analysis_by_id[cleaned.external_id],
        )
        for cleaned in cleaned_lookups
    ]

    definitions = _decide_definitions(analyzed, lexicon)

    grouped: dict[tuple[str, str], list[_AnalyzedLookup]] = defaultdict(list)
    for item in analyzed:
        grouped[item.identity].append(item)

    entries = []
    for (lemma, lang), group in grouped.items():
        first = min(group, key=lambda item: item.looked_up_at)
        entries.append(
            Entry.new(
                word=LookedUpWord(text=first.term, lang=lang),
                lemma=lemma,
                external_id=f"{lang}:{lemma}",
                contexts=[
                    _to_context(item, definitions.get(item.external_id))
                    for item in group
                ],
            )
        )
    return entries


def _decide_definitions(
    analyzed: list[_AnalyzedLookup], lexicon: Lexicon
) -> dict[str, DefinitionDecision]:
    """La decisión de la política de D-025 para cada consulta con categoría,
    por `external_id`, con una sola consulta al léxico para todo el lote.

    Una consulta sin `pos` (el normalizador no localizó la palabra, D-016) no
    se evalúa y no aparece en el resultado: su contexto queda sin decisión,
    que no es lo mismo que `pos_unmapped`.

    Se evalúa el lote entero, también lo que ya está guardado. No cambia nada:
    el repositorio no toca los contextos existentes (D-012), así que esas
    decisiones se descartan al guardar.
    """
    evaluated = [item for item in analyzed if item.analysis.pos is not None]
    facts = lexicon.facts(
        [
            LexiconQuery(
                external_id=item.external_id,
                term=item.term,
                lemma=item.analysis.lemma,
                pos=item.analysis.pos,
                lang=item.lang,
            )
            for item in evaluated
        ]
    )
    return {
        item.external_id: decide_definition(
            item.analysis.lemma, item.analysis.particle, facts[item.external_id]
        )
        for item in evaluated
    }


def _to_context(
    item: _AnalyzedLookup, definition: DefinitionDecision | None
) -> Context:
    return Context(
        external_id=item.lookup.external_id,
        term=item.term,
        raw_sentence=item.lookup.sentence,
        clean_sentence=item.clean_sentence,
        is_truncated=is_truncated(item.clean_sentence),
        captured_at=item.looked_up_at,
        pos=item.analysis.pos,
        morph=item.analysis.morph,
        book_title=item.lookup.book_title,
        book_lang=item.lookup.book_lang,
        particle=item.analysis.particle,
        definition=definition,
    )
