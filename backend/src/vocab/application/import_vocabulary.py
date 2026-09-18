"""Caso de uso: importar vocabulario desde una fuente."""

from collections import defaultdict
from collections.abc import Callable, Iterable

from vocab.adapters.nlp.cleaning import clean_sentence, is_truncated
from vocab.adapters.nlp.normalizer import CleanedLookup, NormalizedWord
from vocab.domain.models import Context, Entry
from vocab.ports.importer import RawLookup, VocabularyImporter
from vocab.ports.repository import ImportStats, VocabularyRepository

# El normalizador entra por parámetro para poder sustituirlo en los tests
# por uno falso, sin cargar spaCy.
Normalizer = Callable[[list[CleanedLookup]], list[tuple[RawLookup, NormalizedWord]]]


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

    El orden importa: la limpieza va antes que spaCy porque el segmentador
    se atraganta con las notas al pie, y la lematización va antes que la
    agrupación porque la identidad de una entrada es su lema.
    """
    # La frase limpia se calcula una sola vez y se reutiliza: la necesita
    # el normalizador y también el contexto que se persiste.
    cleaned_by_lookup: dict[str, str] = {}
    cleaned_lookups: list[CleanedLookup] = []
    for lookup in lookups:
        cleaned = clean_sentence(lookup.sentence)
        cleaned_by_lookup[lookup.external_id] = cleaned
        cleaned_lookups.append(CleanedLookup(cleaned, lookup))

    # `normalize` reordena al agrupar por idioma, así que no se puede
    # emparejar por posición con la lista de entrada.
    normalized = normalizer(cleaned_lookups)

    grouped: dict[tuple[str, str], list[tuple[RawLookup, NormalizedWord]]] = (
        defaultdict(list)
    )
    for lookup, word in normalized:
        grouped[(word.lemma, lookup.lang)].append((lookup, word))

    entries = []
    for (lemma, lang), group in grouped.items():
        first_lookup, first_word = min(group, key=lambda pair: pair[0].looked_up_at)
        entries.append(
            Entry(
                term=first_lookup.word,
                lemma=lemma,
                lang=lang,
                pos=first_word.pos,
                external_id=f"{lang}:{lemma}",
                contexts=[
                    _to_context(lookup, cleaned_by_lookup[lookup.external_id])
                    for lookup, _ in group
                ],
            )
        )
    return entries


def _to_context(lookup: RawLookup, cleaned: str) -> Context:
    return Context(
        external_id=lookup.external_id,
        raw_sentence=lookup.sentence,
        clean_sentence=cleaned,
        is_truncated=is_truncated(cleaned),
        captured_at=lookup.looked_up_at,
        book_title=lookup.book_title,
        book_lang=lookup.book_lang,
    )
