"""La CLI de extremo a extremo contra el Postgres de testcontainers.

Prueba lo que solo existe en la raíz de composición: que la configuración llega
por `DATABASE_URL`, que los adaptadores quedan cableados, que la transacción
se confirma donde debe y cómo se comporta `study` sin modelo. Las reglas del
ejercicio y la elección al azar tienen sus propios tests unitarios.

Ningún test usa Ollama de verdad: el de un Ollama inalcanzable apunta a un
puerto sin servicio.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from vocab.adapters.postgres.base import Base
from vocab.adapters.postgres.repository import PostgresVocabularyRepository
from vocab.adapters.postgres.tables import (
    ContextRow,
    DefinitionFlagRow,
    EntryRow,
    ExerciseRow,
    UserRow,
)
from vocab.cli.main import app
from vocab.config import get_settings
from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.exercises.cloze_original import BLANK
from vocab.domain.models import Context, Entry, EntryStatus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "vocab_fixture.db"

# Lo que configura el modelo y Ollama. Un `.env` de desarrollo lo define, y los
# módulos de integración que llaman a `load_dotenv` lo dejan en el entorno.
MODEL_VARIABLES = (
    "LLM_TASK__DISTRACTORS__PROVIDER",
    "LLM_TASK__DISTRACTORS__MODEL",
    "LLM_TASK__DISTRACTORS__PROMPT_VERSION",
    "LLM_TASK__DISTRACTORS__THINK",
    "LLM_TASK__DISTRACTORS__TEMPERATURE",
    "OLLAMA_BASE_URL",
    "OLLAMA_LOAD_TIMEOUT_SECONDS",
    "OLLAMA_TIMEOUT_SECONDS",
)
# Un puerto sin servicio: la conexión se rechaza al momento.
UNREACHABLE = "http://127.0.0.1:1"

runner = CliRunner()


@pytest.fixture
def database(engine, monkeypatch, tmp_path):
    """La CLI lee la configuración como en producción, con dos cambios.

    - `DATABASE_URL` apunta al contenedor.
    - Sin modelo: con el `.env` de desarrollo, `study` cargaría el modelo
      real en Ollama. Sus variables se borran del entorno, y el directorio de
      trabajo vacío deja fuera los `.env`. El léxico sí hace falta para
      importar, así que su directorio pasa al entorno antes.

    `get_settings` está cacheada, así que se vacía antes y después. La CLI
    confirma con sus propias sesiones, así que las tablas se vacían a mano.
    """
    get_settings.cache_clear()
    wn_data_dir = get_settings().wn_data_dir
    if wn_data_dir is not None:
        monkeypatch.setenv("WN_DATA_DIR", str(wn_data_dir))
    for name in MODEL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield engine
    get_settings.cache_clear()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


def _count(engine: Engine, table: type[Base]) -> int:
    """Cuenta desde una sesión nueva: solo ve lo que alguien confirmó."""
    with Session(engine) as session:
        return session.execute(select(func.count()).select_from(table)).scalar_one()


def _only_in_study(engine: Engine, lemma: str) -> None:
    """Deja una sola entrada `learning`, para que el azar no tenga dónde
    elegir."""
    with engine.begin() as connection:
        connection.execute(
            update(EntryRow).where(EntryRow.lemma != lemma).values(status="known")
        )


def _add_known_past_verbs(
    engine: Engine, *terms: str, definitions: tuple[str, ...] = ()
) -> None:
    """Entradas `known` en pasado: con `relied` del fixture, dan a `eased` los
    tres distractores de la variante de elección.

    Con `definitions`, cada una lleva la suya, `eligible`: son las que dan a
    `rely` los tres distractores de la plantilla.
    """
    decisions: list[DefinitionDecision | None] = [None] * len(terms)
    if definitions:
        decisions = [
            DefinitionDecision(
                DefinitionStatus.ELIGIBLE,
                "oewn:2025",
                definition=definition,
                sense_id=f"{term}-v-1",
            )
            for term, definition in zip(terms, definitions, strict=True)
        ]
    with Session(engine) as session:
        repository = PostgresVocabularyRepository(session)
        user_id = repository.ensure_user()
        source_id = repository.register_source(user_id, "test", "test", "extra")
        entries = [
            Entry(
                term=term,
                lemma=term,
                lang="en",
                status=EntryStatus.KNOWN,
                contexts=[
                    Context(
                        external_id=f"extra:{term}",
                        term=term,
                        raw_sentence=f"They {term} it.",
                        clean_sentence=f"They {term} it.",
                        is_truncated=False,
                        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
                        pos="VERB",
                        morph="Tense=Past|VerbForm=Fin",
                        definition=decision,
                    )
                ],
            )
            for term, decision in zip(terms, decisions, strict=True)
        ]
        repository.upsert_entries(user_id, source_id, entries)
        session.commit()


@pytest.mark.usefixtures("lexicon")
def test_import_commits_what_it_imports(database):
    result = runner.invoke(app, ["import", str(FIXTURE)])

    assert result.exit_code == 0, result.output
    assert "Entradas: 5 nuevas, 0 ya existían." in result.output
    assert "Contextos: 8 nuevos, 0 ya existían." in result.output
    assert _count(database, EntryRow) == 5
    assert _count(database, ContextRow) == 8
    # El léxico queda cableado: cada contexto con categoría trae su decisión,
    # con el léxico que la produjo, y uno sin categoría no (D-033).
    with Session(database) as session:
        rows = session.execute(
            select(ContextRow.pos, ContextRow.definition_status, ContextRow.lexicon)
        ).all()
    assert {(pos is None, status is None) for pos, status, _ in rows} <= {
        (True, True),
        (False, False),
    }
    assert {lexicon for _, status, lexicon in rows if status} == {"oewn:2025"}


def test_import_without_lexicon_directory_fails_before_touching_the_database(
    database, monkeypatch, tmp_path
):
    """Sin WN_DATA_DIR no se importa nada, ni siquiera a medias. El directorio
    de trabajo vacío deja fuera el `.env` que lo define."""
    monkeypatch.delenv("WN_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    result = runner.invoke(app, ["import", str(FIXTURE)])

    assert result.exit_code == 1
    assert "Falta WN_DATA_DIR" in result.output
    assert _count(database, UserRow) == 0


def test_import_of_a_missing_file_fails_before_touching_the_database(
    database, tmp_path
):
    result = runner.invoke(app, ["import", str(tmp_path / "vocab.db")])

    assert result.exit_code == 2
    assert "does not exist" in result.output
    assert _count(database, UserRow) == 0


def test_study_with_nothing_to_study_says_so_and_writes_nothing(database):
    """`ensure_user` crea el usuario en una base vacía; `study` nunca
    confirma, así que no queda escrito."""
    result = runner.invoke(app, ["study"])

    assert result.exit_code == 0, result.output
    assert "No hay entradas en estudio" in result.output
    assert _count(database, UserRow) == 0


@pytest.mark.usefixtures("lexicon")
def test_study_accepts_the_answer_ignoring_case_and_spaces(database):
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "stake")

    result = runner.invoke(app, ["study", "--write"], input="  STAKE \n")

    assert result.exit_code == 0, result.output
    assert f"He held a {BLANK} in the company." in result.output
    assert "Correcto." in result.output
    assert "1 de 1 correctas." in result.output


@pytest.mark.usefixtures("lexicon")
def test_study_shows_the_word_and_the_clean_sentence_after_a_miss(database):
    """El contexto de `brow` llega sucio (`…more.[59].[`): tras el fallo se
    muestra la frase limpia, no la cruda."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "brow")

    result = runner.invoke(app, ["study", "--write"], input="brows\n")

    assert result.exit_code == 0, result.output
    assert "Incorrecto. La palabra era «brow»." in result.output
    assert "Frase: He wiped his brow and said nothing more." in result.output
    assert "[59]" not in result.output
    assert "0 de 1 correctas." in result.output


@pytest.mark.usefixtures("lexicon")
def test_study_offers_four_options_and_takes_the_number(database):
    """El orden de las opciones es aleatorio: el test lee cuál es la 1 y
    comprueba que el veredicto le corresponde."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "ease")
    _add_known_past_verbs(database, "tossed", "waned")

    result = runner.invoke(app, ["study"], input="1\n")

    assert result.exit_code == 0, result.output
    assert "Sin opciones" not in result.output
    first_exercise = result.output.split("Elige (1-4)")[0]
    options = dict(re.findall(r"^  (\d)\) (\S+)$", first_exercise, re.MULTILINE))
    assert sorted(options.values()) == ["eased", "relied", "tossed", "waned"]
    verdicts = re.findall(r"^(Correcto|Incorrecto)", result.output, re.MULTILINE)
    assert verdicts == ["Correcto" if options["1"] == "eased" else "Incorrecto"]


@pytest.mark.usefixtures("lexicon")
def test_study_asks_again_when_the_answer_is_not_an_option_number(database):
    """La palabra escrita, una línea vacía o un número fuera del rango no
    eligen ninguna opción: se vuelve a preguntar, sin contarlos como fallo."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "ease")
    _add_known_past_verbs(database, "tossed", "waned")

    result = runner.invoke(app, ["study"], input="eased\n\n9\n1\n")

    assert result.exit_code == 0, result.output
    assert result.output.count("Escribe un número del 1 al 4.") == 3
    assert result.output.count("Elige (1-4)") == 5
    assert len(re.findall(r"^(Correcto|Incorrecto)", result.output, re.MULTILINE)) == 1
    assert "de 1 correctas." in result.output


@pytest.mark.usefixtures("lexicon")
def test_study_without_three_distractors_asks_to_write_and_says_why(database):
    """`stake` solo comparte forma con `brow`: el aviso dice cuántas hay, cuál
    es la forma y por qué hacen falta tres."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "stake")

    result = runner.invoke(app, ["study"], input="stake\n")

    assert result.exit_code == 0, result.output
    assert (
        "Sin opciones: solo otra de tus palabras consultadas tiene su misma forma "
        "gramatical (NOUN Number=Sing), y hacen falta 3 para que la gramática no "
        "delate la respuesta. Escríbela."
    ) in result.output
    assert "Elige" not in result.output
    assert "Correcto." in result.output


@pytest.mark.usefixtures("lexicon")
def test_study_write_asks_to_type_even_when_there_are_options(database):
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "ease")
    _add_known_past_verbs(database, "tossed", "waned")

    result = runner.invoke(app, ["study", "--write"], input="eased\n")

    assert result.exit_code == 0, result.output
    assert f"Electronics {BLANK} out hydraulics in the new design." in result.output
    assert ") eased" not in result.output
    assert "Sin opciones" not in result.output
    assert "Correcto." in result.output


@pytest.mark.usefixtures("lexicon")
def test_study_without_a_model_says_so_once_and_uses_the_template(database):
    """Sin tarea configurada, que es como corren estos tests: un aviso al
    empezar y los ejercicios de definición con la plantilla, sin repetirlo.

    `rely` es `eligible` en el fixture; las tres definiciones de las entradas
    `known` le dan la plantilla.
    """
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "rely")
    _add_known_past_verbs(
        database,
        "craved",
        "gulped",
        "levered",
        definitions=(
            "have an urgent desire for",
            "swallow hurriedly or greedily",
            "move or force with a lever",
        ),
    )

    result = runner.invoke(app, ["study"], input="1\n\n1\n\n")

    assert result.exit_code == 0, result.output
    notice = (
        "Sin modelo: la tarea de distractores no está configurada "
        "(LLM_TASK__DISTRACTORS__*). Los ejercicios de definición usan la "
        "plantilla."
    )
    assert result.output.count(notice) == 1
    assert result.output.index(notice) < result.output.index("Elige")
    assert result.output.count("Definición: ") == 2
    assert "Distractores de la plantilla" not in result.output
    assert "de 2 correctas." in result.output
    # Enter tras la definición sigue sin marcar nada.
    assert _count(database, DefinitionFlagRow) == 0


@pytest.mark.usefixtures("lexicon")
def test_failed_warm_up_leaves_the_session_without_model_with_one_notice(
    database, monkeypatch
):
    """Ollama no responde al empezar: un solo aviso, con la URL y el modelo,
    y la sesión entera con la plantilla, sin volver a intentarlo en cada
    ejercicio. El modelo es un nombre cualquiera: no se llega a pedir."""
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "rely")
    _add_known_past_verbs(
        database,
        "craved",
        "gulped",
        "levered",
        definitions=(
            "have an urgent desire for",
            "swallow hurriedly or greedily",
            "move or force with a lever",
        ),
    )
    monkeypatch.setenv("LLM_TASK__DISTRACTORS__PROVIDER", "ollama")
    monkeypatch.setenv("LLM_TASK__DISTRACTORS__MODEL", "some-model:4b")
    monkeypatch.setenv("LLM_TASK__DISTRACTORS__PROMPT_VERSION", "v1")
    monkeypatch.setenv("OLLAMA_BASE_URL", UNREACHABLE)
    get_settings.cache_clear()

    result = runner.invoke(app, ["study"], input="1\n\n1\n\n")

    assert result.exit_code == 0, result.output
    notice = (
        f"Sin modelo: Ollama en {UNREACHABLE}/api/ps con el modelo "
        "'some-model:4b': no se pudo conectar"
    )
    assert result.output.count(notice) == 1
    assert result.output.count("Ollama en") == 1
    assert result.output.index(notice) < result.output.index("Elige")
    assert "Cargando el modelo" not in result.output
    assert "Distractores de la plantilla" not in result.output
    assert result.output.count("Definición: ") == 2
    assert "de 2 correctas." in result.output


@pytest.mark.usefixtures("lexicon")
def test_x_after_a_definition_flags_its_context_and_sense(database):
    """Tras el primer ejercicio, de definición, x guarda la marca de su
    contexto con su sentido. Cada ejercicio mostrado queda guardado al
    mostrarse, también el segundo, que se cierra sin responder.

    Los dos contextos utilizables de `rely` en el fixture tienen formas
    distintas (`relied`, `rely`): la resaltada dice cuál salió.
    """
    runner.invoke(app, ["import", str(FIXTURE)])
    _only_in_study(database, "rely")
    _add_known_past_verbs(
        database,
        "craved",
        "gulped",
        "levered",
        definitions=(
            "have an urgent desire for",
            "swallow hurriedly or greedily",
            "move or force with a lever",
        ),
    )

    result = runner.invoke(app, ["study"], input="1\nx\n")

    assert result.exit_code == 0, result.output
    assert "Marcada: este contexto ya no dará ejercicio de definición" in result.output
    with Session(database) as session:
        flagged = session.execute(
            select(
                ContextRow.term, ContextRow.sense_id, DefinitionFlagRow.sense_id
            ).join(DefinitionFlagRow, DefinitionFlagRow.context_id == ContextRow.id)
        ).all()
        kinds = session.scalars(select(ExerciseRow.kind).order_by(ExerciseRow.id)).all()
    assert len(flagged) == 1
    term, context_sense, flagged_sense = flagged[0]
    assert flagged_sense == context_sense
    first_exercise = result.output.split("Marcada")[0]
    assert f"«{term}»" in first_exercise
    assert len(kinds) == 2
    assert kinds[0] == "mcq_definition"
