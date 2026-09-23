"""Caso de uso: importar vocabulario desde una fuente."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from vocab.domain.cleaning import CleanSentence, clean_sentence, is_truncated
from vocab.domain.models import Context, Entry
from vocab.domain.noise import LookedUpWord
from vocab.ports.importer import RawLookup, VocabularyImporter
from vocab.ports.normalizer import CleanedLookup, NormalizedWord, Normalizer
from vocab.ports.repository import ImportStats, VocabularyRepository


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
    repository: VocabularyRepository,
    normalizer: Normalizer,
    filename: str,
) -> ImportStats:
    user_id = repository.ensure_user()
    source_id = repository.register_source(
        user_id=user_id,
        kind=importer.kind,
        filename=filename,
        checksum=importer.checksum(),
    )
    entries = _build_entries(importer.read(), normalizer)
    return repository.upsert_entries(user_id, source_id, entries)


def _build_entries(lookups: Iterable[RawLookup], normalizer: Normalizer) -> list[Entry]:
    """Limpia, normaliza y agrupa las consultas en entradas.

    El orden importa: la limpieza va antes que la normalización porque el
    segmentador se atraganta con las notas al pie, y la normalización va antes
    que la agrupación porque la identidad de una entrada es su lema.

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
                contexts=[_to_context(item) for item in group],
            )
        )
    return entries


def _to_context(item: _AnalyzedLookup) -> Context:
    return Context(
        external_id=item.lookup.external_id,
        raw_sentence=item.lookup.sentence,
        clean_sentence=item.clean_sentence,
        is_truncated=is_truncated(item.clean_sentence),
        captured_at=item.looked_up_at,
        pos=item.analysis.pos,
        book_title=item.lookup.book_title,
        book_lang=item.lookup.book_lang,
    )
