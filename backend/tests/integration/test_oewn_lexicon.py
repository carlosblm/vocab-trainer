"""El adaptador de OEWN con el léxico real, sobre lemas comprobados en él:
`bank` (D-025), `waned` (la medición de D-025) y `sojourned` (comprobado al
escribir este test).

Los que piden `lexicon` se saltan si el léxico no está descargado. El de la
descarga ausente no lo necesita.
"""

from pathlib import Path

import pytest
import wn

from vocab.adapters.lexicon import LexiconNotDownloaded, OewnLexicon
from vocab.domain.definition_policy import DefinitionStatus, decide_definition
from vocab.ports.lexicon import Lexicon, LexiconQuery


def _decide(lexicon: Lexicon, query: LexiconQuery) -> DefinitionStatus:
    facts = lexicon.facts([query])[query.external_id]
    return decide_definition(query.lemma, None, facts).status


def test_bank_as_noun_has_ten_senses_in_lexicon_order(lexicon: OewnLexicon) -> None:
    """El orden importa para la selección de sentido de F4. D-025 lo verificó
    contra el XML: el primer sentido de `bank` es la orilla."""
    query = LexiconQuery("bank", term="banks", lemma="bank", pos="NOUN", lang="en")
    # Asignación tipada: mypy comprueba que el adaptador cumple el puerto.
    port: Lexicon = lexicon

    facts = port.facts([query])["bank"]

    assert facts.term_lemmas == {"bank"}
    assert len(facts.senses) == 10
    assert facts.senses[0].gloss.startswith("sloping land")
    assert _decide(lexicon, query) is DefinitionStatus.POLYSEMOUS


def test_sojourned_leads_to_a_lemma_with_a_single_sense(
    lexicon: OewnLexicon,
) -> None:
    """Comprobado en `oewn:2025` el 2026-10-07: `sojourn` como verbo tiene un
    único sentido, y Morphy lleva `sojourned` a él."""
    query = LexiconQuery(
        "sojourn", term="sojourned", lemma="sojourn", pos="VERB", lang="en"
    )

    facts = lexicon.facts([query])["sojourn"]
    decision = decide_definition(query.lemma, None, facts)

    assert facts.term_lemmas == {"sojourn"}
    assert decision.status is DefinitionStatus.ELIGIBLE
    assert decision.definition == facts.senses[0].gloss
    assert decision.sense_id == facts.senses[0].id


def test_waned_leads_to_wan_and_wane(lexicon: OewnLexicon) -> None:
    """El error de spaCy de D-015: lema `wan`. El léxico lleva la forma a los
    dos, así que no confirma el lema."""
    query = LexiconQuery("waned", term="waned", lemma="wan", pos="VERB", lang="en")

    facts = lexicon.facts([query])["waned"]

    assert facts.term_lemmas == {"wan", "wane"}
    assert _decide(lexicon, query) is DefinitionStatus.LEMMA_DISAGREES


def test_one_result_per_query_also_without_category(lexicon: OewnLexicon) -> None:
    queries = [
        LexiconQuery("a", term="Bevel", lemma="Bevel", pos="PROPN", lang="en"),
        LexiconQuery("b", term="Bevel", lemma="Bevel", pos=None, lang="en"),
        LexiconQuery("c", term="craved", lemma="crave", pos="VERB", lang="en"),
    ]

    facts = lexicon.facts(queries)

    assert set(facts) == {"a", "b", "c"}
    assert not facts["a"].pos_supported
    assert not facts["b"].pos_supported
    assert facts["c"].pos_supported


def test_language_without_lexicon_is_a_value_error(lexicon: OewnLexicon) -> None:
    """Todo el lote falla, aunque solo una consulta sea de otro idioma: es un
    error de quien llama, como en los validadores (D-027)."""
    queries = [
        LexiconQuery("en", term="banks", lemma="bank", pos="NOUN", lang="en"),
        LexiconQuery("es", term="bancos", lemma="banco", pos="NOUN", lang="es"),
    ]

    with pytest.raises(ValueError, match="solo es de inglés.*'es'"):
        lexicon.facts(queries)


@pytest.fixture
def restore_wn_directory():
    """`wn.config` es global: se deja como estaba para el resto de tests.
    `database_path.parent` da el directorio sin crearlo, al revés que
    `data_directory`."""
    previous = wn.config.database_path.parent
    yield
    wn.config.data_directory = previous


def test_missing_lexicon_fails_on_construction_with_how_to_download(
    tmp_path: Path, restore_wn_directory: None
) -> None:
    with pytest.raises(LexiconNotDownloaded) as error:
        OewnLexicon(tmp_path)

    assert f"--dir {tmp_path} download oewn:2025" in str(error.value)
    # No abre la base: `wn` habría creado una vacía.
    assert list(tmp_path.iterdir()) == []
