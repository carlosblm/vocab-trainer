"""Caso de uso: importar vocabulario desde una fuente."""

from collections import defaultdict

from vocab.domain.models import Context, Entry
from vocab.ports.importer import RawLookup, VocabularyImporter
from vocab.ports.repository import ImportStats, VocabularyRepository


def import_vocabulary(
    importer: VocabularyImporter,
    repository: VocabularyRepository,
    filename: str,
) -> ImportStats:
    user_id = repository.ensure_user()
    source_id = repository.register_source(
        user_id=user_id,
        kind=importer.kind,
        filename=filename,
        checksum=importer.checksum(),
    )
    entries = _group_by_lemma(importer.read())
    return repository.upsert_entries(user_id, source_id, entries)


def _group_by_lemma(lookups) -> list[Entry]:
    """Agrupa consultas en entradas.

    F0.3 usa la palabra en minúsculas como lema provisional (será
    sustituido por la limpieza realizada posteriormente con spacy)
    """
    grouped: dict[tuple[str, str], list[RawLookup]] = defaultdict(list)
    for lookup in lookups:
        grouped[(lookup.word.lower(), lookup.lang)].append(lookup)

    entries = []
    for (lemma, lang), group in grouped.items():
        first = min(group, key=lambda lk: lk.looked_up_at)
        entries.append(
            Entry(
                term=first.word,
                lemma=lemma,
                lang=lang,
                external_id=f"{lang}:{lemma}",
                contexts=[_to_context(lk) for lk in group],
            )
        )
    return entries


def _to_context(lookup: RawLookup) -> Context:
    # Será sustituido por la limpieza real con spaCy.
    return Context(
        external_id=lookup.external_id,
        raw_sentence=lookup.sentence,
        clean_sentence=lookup.sentence.strip(),
        is_truncated=False,
        captured_at=lookup.looked_up_at,
        book_title=lookup.book_title,
        book_lang=lookup.book_lang,
    )
