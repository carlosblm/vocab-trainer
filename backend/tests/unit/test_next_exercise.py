"""Prueba el caso de uso `next_exercise` con un repositorio falso, el doble del
generador y un azar controlado: sin base de datos ni modelo, y con resultado
determinista.

Este módulo no importa nada de `vocab.adapters`.
"""

import logging
import random
from datetime import UTC, datetime

import pytest
from tests.unit.doubles import ScriptedDistractorGenerator

from vocab.application.generate_distractors import (
    MAX_RETRIES,
    AcceptedAttempt,
    MalformedAttempt,
    ProviderUnavailable,
    RetriesExhausted,
    UnavailableAttempt,
)
from vocab.application.next_exercise import (
    ChoiceFallback,
    ClozeExercise,
    DefinitionExercise,
    DefinitionFallback,
    ExerciseRejected,
    ModelDistractors,
    NoGenerator,
    TemplateDistractors,
    next_exercise,
)
from vocab.domain.cleaning import CleanSentence
from vocab.domain.definition_policy import DefinitionDecision, DefinitionStatus
from vocab.domain.exercises.cloze_original import ClozeOriginal
from vocab.domain.exercises.cloze_original_choice import ClozeOriginalChoice
from vocab.domain.exercises.definition_template import DefinitionCandidate
from vocab.domain.exercises.mcq_definition import McqDefinition
from vocab.domain.models import Context, ContextKey, DefinitionFlag, Entry
from vocab.ports.distractor_generator import (
    DistractorRequest,
    GeneratedDistractors,
    GeneratorIdentity,
    GeneratorUnavailable,
    MalformedOutput,
)

PAST = "Tense=Past|VerbForm=Fin"


class FakeRepository:
    """Devuelve las entradas que recibe y anota qué se le pidió.

    `candidates` son las entradas de las que salen los distractores de
    `cloze_original`; `definitions`, las definiciones de las que sale la
    plantilla de `mcq_definition`; y `flags`, las marcas «la definición no
    encaja». Por defecto, ninguna.
    """

    def __init__(
        self,
        entries: list[Entry],
        candidates: list[Entry] | None = None,
        definitions: list[DefinitionCandidate] | None = None,
        flags: frozenset[DefinitionFlag] = frozenset(),
    ) -> None:
        self._entries = entries
        self._candidates = candidates or []
        self._definitions = definitions or []
        self._flags = flags
        self.requested_user_ids: list[int] = []
        self.candidate_reads = 0
        self.definition_reads = 0

    def ensure_user(self) -> int:
        return 7

    def list_learning_entries_with_usable_context(self, user_id: int) -> list[Entry]:
        self.requested_user_ids.append(user_id)
        return self._entries

    def list_non_noise_entries(self, user_id: int) -> list[Entry]:
        self.candidate_reads += 1
        return self._candidates

    def list_definition_candidates(self, user_id: int) -> list[DefinitionCandidate]:
        self.definition_reads += 1
        return self._definitions

    def list_definition_flags(self, user_id: int) -> frozenset[DefinitionFlag]:
        return self._flags


class InOrder(random.Random):
    """Azar trucado: toda permutación deja la población en su orden."""

    def sample(self, population, k, *, counts=None):
        return list(population)[:k]

    def shuffle(self, x):
        pass


class Reversed(random.Random):
    """Azar trucado: toda permutación invierte la población."""

    def sample(self, population, k, *, counts=None):
        return list(reversed(population))[:k]


def _context(
    external_id: str,
    term: str,
    sentence: str,
    *,
    raw: str | None = None,
    truncated: bool = False,
    pos: str | None = None,
    morph: str | None = None,
    definition: DefinitionDecision | None = None,
) -> Context:
    return Context(
        external_id=external_id,
        term=term,
        raw_sentence=raw if raw is not None else sentence,
        clean_sentence=sentence,
        is_truncated=truncated,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        pos=pos,
        morph=morph,
        definition=definition,
    )


def _entry(lemma: str, contexts: list[Context], term: str | None = None) -> Entry:
    return Entry(
        term=term or contexts[0].term, lemma=lemma, lang="en", contexts=contexts
    )


def _past(lemma: str, term: str) -> Entry:
    return _entry(
        lemma, [_context(f"c-{term}", term, f"They {term} it.", pos="VERB", morph=PAST)]
    )


def _writing(repository: FakeRepository, rng: random.Random) -> ClozeOriginal | None:
    """La variante de escritura, que es la que usan los tests de selección."""
    item = next_exercise(repository, None, rng, choice=False)
    if item is None:
        return None
    assert isinstance(item, ClozeExercise)
    assert isinstance(item.exercise, ClozeOriginal)
    assert item.fallback is None
    return item.exercise


# --- Selección de entrada y contexto


def test_nothing_to_study_gives_none():
    assert (
        next_exercise(FakeRepository([]), None, random.Random(0), choice=True) is None
    )


def test_entries_are_requested_for_the_single_user():
    repository = FakeRepository([])

    next_exercise(repository, None, random.Random(0), choice=False)

    assert repository.requested_user_ids == [7]


def test_word_and_clean_sentence_come_from_the_context_not_the_entry():
    """La entrada guarda `relied`; este contexto se consultó como `rely`
    (D-020). La frase es la limpia, que es la que se muestra tras un fallo."""
    context = _context("l2", "rely", "I rely on you.", raw=" I rely on you.[59] ")
    repository = FakeRepository([_entry("rely", [context], term="relied")])

    exercise = _writing(repository, random.Random(0))

    assert exercise is not None
    assert exercise.word == "rely"
    assert exercise.sentence == "I rely on you."


def test_rng_chooses_the_entry_and_then_the_context():
    entries = [
        _entry(
            "tide",
            [
                _context("t1", "tide", "The tide rose."),
                _context("t2", "tides", "The tides fell."),
            ],
        ),
        _entry(
            "rely",
            [
                _context("r1", "relied", "She relied on luck."),
                _context("r2", "rely", "I rely on you."),
            ],
        ),
    ]
    repository = FakeRepository(entries)

    first = _writing(repository, InOrder())
    last = _writing(repository, Reversed())

    assert first is not None and first.sentence == "The tide rose."
    assert last is not None and last.sentence == "I rely on you."


def test_only_usable_contexts_are_candidates():
    """El truncado va primero y el azar en orden lo elegiría si contara."""
    entry = _entry(
        "rely",
        [
            _context("l1", "relied", "They relied on the", truncated=True),
            _context("l2", "rely", "I rely on you."),
        ],
    )

    exercise = _writing(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."


def test_same_seed_gives_the_same_exercise():
    entries = [
        _entry(f"word{i}", [_context(f"l{i}", f"word{i}", f"A word{i} here.")])
        for i in range(50)
    ]
    repository = FakeRepository(entries)

    first = _writing(repository, random.Random(42))
    second = _writing(repository, random.Random(42))

    assert first == second


def test_context_without_the_word_is_skipped_with_a_warning(caplog):
    entry = _entry(
        "rely",
        [
            _context("broken", "rely", "Nothing to see here."),
            _context("good", "rely", "I rely on you."),
        ],
    )

    with caplog.at_level(logging.WARNING):
        exercise = _writing(FakeRepository([entry]), InOrder())

    assert exercise is not None and exercise.sentence == "I rely on you."
    assert "broken" in caplog.text


def test_entry_whose_contexts_all_fail_gives_way_to_another():
    entries = [
        _entry("rely", [_context("broken", "rely", "Nothing to see here.")]),
        _entry("tide", [_context("good", "tide", "The tide rose.")]),
    ]

    exercise = _writing(FakeRepository(entries), InOrder())

    assert exercise is not None and exercise.sentence == "The tide rose."


def test_no_context_admitting_an_exercise_gives_none(caplog):
    entries = [_entry("rely", [_context("broken", "rely", "Nothing to see here.")])]

    with caplog.at_level(logging.WARNING):
        exercise = _writing(FakeRepository(entries), random.Random(0))

    assert exercise is None
    assert "broken" in caplog.text


# --- Variante de elección (D-022)

TARGET = _entry(
    "rely",
    [_context("r1", "relied", "She relied on luck.", pos="VERB", morph=PAST)],
)


def test_choice_gives_the_cloze_of_the_chosen_context_and_four_options():
    """La entrada elegida también llega entre los candidatos, como en la base:
    la regla la descarta por lema."""
    candidates = [TARGET, _past("toss", "tossed"), _past("ease", "eased")]
    candidates.append(_past("wane", "waned"))
    repository = FakeRepository([TARGET], candidates)

    item = next_exercise(repository, None, InOrder(), choice=True)

    assert isinstance(item, ClozeExercise) and item.fallback is None
    assert isinstance(item.exercise, ClozeOriginalChoice)
    assert item.exercise.cloze == ClozeOriginal("She relied on luck.", "relied")
    assert item.exercise.options == ("relied", "tossed", "eased", "waned")


def test_choice_without_enough_distractors_falls_back_to_writing_and_says_why():
    repository = FakeRepository([TARGET], [TARGET, _past("toss", "tossed")])

    item = next_exercise(repository, None, InOrder(), choice=True)

    assert isinstance(item, ClozeExercise)
    assert item.exercise == ClozeOriginal("She relied on luck.", "relied")
    assert item.fallback == ChoiceFallback(
        pos="VERB", morph=PAST, available=1, needed=3
    )


def test_fallback_of_an_unanalyzed_answer_says_there_is_no_form_to_match():
    entry = _entry("rely", [_context("r1", "relied", "She relied on luck.")])
    candidates = [_past(lemma, f"{lemma}ed") for lemma in ("toss", "ease", "wane")]

    item = next_exercise(
        FakeRepository([entry], candidates), None, InOrder(), choice=True
    )

    assert isinstance(item, ClozeExercise)
    assert item.fallback == ChoiceFallback(pos=None, morph=None, available=0, needed=3)


def test_candidates_are_read_only_for_the_choice_variant():
    repository = FakeRepository([TARGET])

    next_exercise(repository, None, random.Random(0), choice=False)
    assert repository.candidate_reads == 0

    next_exercise(repository, None, random.Random(0), choice=True)
    assert repository.candidate_reads == 1


def test_same_seed_gives_the_same_options():
    candidates = [
        _past(lemma, f"{lemma}ed") for lemma in ("toss", "ease", "wane", "jump", "kick")
    ]
    repository = FakeRepository([TARGET], candidates)

    first = next_exercise(repository, None, random.Random(42), choice=True)
    second = next_exercise(repository, None, random.Random(42), choice=True)

    assert first == second


# --- mcq_definition (§7.3)

SOJOURN = "spend a certain length of time; reside temporarily"
SENTENCE = "They sojourned in the hills."


def _sojourned(definition: DefinitionDecision | None) -> Entry:
    return _entry(
        "sojourn",
        [
            _context(
                "s1",
                "sojourned",
                SENTENCE,
                pos="VERB",
                morph=PAST,
                definition=definition,
            )
        ],
    )


SOJOURNED = _sojourned(
    DefinitionDecision(
        DefinitionStatus.ELIGIBLE,
        "oewn:2025",
        definition=SOJOURN,
        sense_id="sojourn-v-1",
    )
)
FROM_MODEL = GeneratedDistractors(
    distractors=(
        "travel quickly from one place to another",
        "speak in a low and quiet voice",
        "work hard for a long period of time",
    ),
)
# La identidad del doble del generador, con sus valores por defecto.
SCRIPTED = GeneratorIdentity("scripted", "test")
# Las definiciones de las que sale la plantilla: tres, las justas.
DEFINITIONS = [
    DefinitionCandidate(
        "crave", "en", "VERB", "crave-v-1", "have an urgent desire for"
    ),
    DefinitionCandidate(
        "gulp", "en", "VERB", "gulp-v-1", "swallow hurriedly or greedily"
    ),
    DefinitionCandidate(
        "lever", "en", "VERB", "lever-v-1", "move or force with a lever"
    ),
]
TEMPLATE = {candidate.definition for candidate in DEFINITIONS}
# Los distractores de la variante de elección de `cloze_original`.
PAST_VERBS = [_past("toss", "tossed"), _past("ease", "eased"), _past("wane", "waned")]
UNAVAILABLE = "Ollama en http://localhost:1/api/chat: no se pudo conectar"


def test_eligible_context_gives_mcq_definition_with_the_model_distractors():
    repository = FakeRepository([SOJOURNED], definitions=DEFINITIONS)
    generator = ScriptedDistractorGenerator([FROM_MODEL])

    item = next_exercise(repository, generator, InOrder(), choice=True)

    assert isinstance(item, DefinitionExercise)
    assert item.exercise == McqDefinition(
        SENTENCE, "sojourned", SOJOURN, (SOJOURN, *FROM_MODEL.distractors)
    )
    assert item.source == ModelDistractors(SCRIPTED, (AcceptedAttempt(),))
    assert (item.entry, item.context) == (SOJOURNED, SOJOURNED.contexts[0])
    # La petición lleva los datos del contexto: su forma, su categoría, su
    # frase y su definición, con el lema y el idioma de la entrada.
    assert generator.requests == [
        DistractorRequest(
            term="sojourned",
            lemma="sojourn",
            pos="VERB",
            sentence=CleanSentence(SENTENCE),
            definition=SOJOURN,
            lang="en",
        )
    ]
    # Con el modelo respondiendo, la plantilla no hace falta y no se lee.
    assert repository.definition_reads == 0


@pytest.mark.parametrize(
    ("outcomes", "cause", "attempts"),
    [
        (
            [GeneratorUnavailable(UNAVAILABLE)],
            ProviderUnavailable(UNAVAILABLE),
            (UnavailableAttempt(UNAVAILABLE),),
        ),
        (
            [MalformedOutput("no es JSON")] * (1 + MAX_RETRIES),
            RetriesExhausted(),
            (MalformedAttempt("no es JSON"),) * (1 + MAX_RETRIES),
        ),
    ],
    ids=["provider_unavailable", "retries_exhausted"],
)
def test_degraded_generation_goes_to_the_template_with_its_cause(
    outcomes, cause, attempts
):
    """Degradó, pero se intentó con un generador: su configuración va en el
    resultado, para guardarla con el ejercicio."""
    repository = FakeRepository([SOJOURNED], definitions=DEFINITIONS)

    item = next_exercise(
        repository, ScriptedDistractorGenerator(outcomes), InOrder(), choice=True
    )

    assert isinstance(item, DefinitionExercise)
    assert item.source == TemplateDistractors(cause, attempts, SCRIPTED)
    assert item.exercise.definition == SOJOURN
    assert set(item.exercise.distractors) == TEMPLATE


def test_without_template_the_context_goes_to_cloze_original_and_says_why():
    """Dos definiciones no llegan a tres. El contexto sigue siendo el mismo, en
    la variante de elección de `cloze_original`, y el resultado lleva por qué
    no hubo `mcq_definition`."""
    repository = FakeRepository([SOJOURNED], PAST_VERBS, DEFINITIONS[:2])
    generator = ScriptedDistractorGenerator([GeneratorUnavailable(UNAVAILABLE)])

    item = next_exercise(repository, generator, InOrder(), choice=True)

    assert isinstance(item, ClozeExercise)
    assert isinstance(item.exercise, ClozeOriginalChoice)
    assert item.exercise.cloze == ClozeOriginal(SENTENCE, "sojourned")
    assert item.fallback is None
    assert item.definition_fallback == DefinitionFallback(
        ProviderUnavailable(UNAVAILABLE), (UnavailableAttempt(UNAVAILABLE),), SCRIPTED
    )


@pytest.mark.parametrize(
    "decision",
    [None, DefinitionDecision(DefinitionStatus.POLYSEMOUS, "oewn:2025")],
    ids=["not_evaluated", "polysemous"],
)
def test_context_that_is_not_eligible_gives_cloze_original_without_the_model(
    decision,
):
    """El doble sin guion falla si se le llama."""
    repository = FakeRepository([_sojourned(decision)], PAST_VERBS, DEFINITIONS)
    generator = ScriptedDistractorGenerator([])

    item = next_exercise(repository, generator, InOrder(), choice=True)

    assert isinstance(item, ClozeExercise)
    assert isinstance(item.exercise, ClozeOriginalChoice)
    assert item.definition_fallback is None
    assert generator.requests == []
    assert repository.definition_reads == 0


def test_without_generator_eligible_context_goes_to_the_template_and_says_so():
    repository = FakeRepository([SOJOURNED], definitions=DEFINITIONS)

    item = next_exercise(repository, None, InOrder(), choice=True)

    assert isinstance(item, DefinitionExercise)
    assert item.source == TemplateDistractors(NoGenerator(), (), generator=None)
    assert set(item.exercise.distractors) == TEMPLATE


def test_model_distractors_the_exercise_rejects_go_to_the_template(monkeypatch):
    """Con los validadores de hoy no puede pasar: comprueban lo mismo que las
    invariantes de `McqDefinition`. Para ver la red de seguridad, el test les
    abre un hueco: el validador del bucle lo da todo por bueno, y el modelo
    repite un distractor con otra mayúscula y otra puntuación."""
    monkeypatch.setattr(
        "vocab.application.generate_distractors.validate_distractors",
        lambda *args: (),
    )
    repeated = GeneratedDistractors(
        distractors=("speak quietly", "Speak quietly.", "work hard"),
    )
    repository = FakeRepository([SOJOURNED], definitions=DEFINITIONS)

    item = next_exercise(
        repository, ScriptedDistractorGenerator([repeated]), InOrder(), choice=True
    )

    assert isinstance(item, DefinitionExercise)
    assert item.source == TemplateDistractors(
        ExerciseRejected("hay opciones repetidas", repeated),
        (AcceptedAttempt(),),
        SCRIPTED,
    )
    assert set(item.exercise.distractors) == TEMPLATE


def test_writing_variant_never_asks_for_distractors():
    """`mcq_definition` es de opción múltiple y no tiene variante de escritura:
    con `--write`, un contexto `eligible` también es `cloze_original`."""
    generator = ScriptedDistractorGenerator([])
    repository = FakeRepository([SOJOURNED], definitions=DEFINITIONS)

    item = next_exercise(repository, generator, InOrder(), choice=False)

    assert item == ClozeExercise(
        SOJOURNED, SOJOURNED.contexts[0], ClozeOriginal(SENTENCE, "sojourned")
    )
    assert generator.requests == []


# --- Marca «la definición no encaja»


def _flag(sense_id: str) -> DefinitionFlag:
    return DefinitionFlag(
        context=ContextKey(lemma="sojourn", lang="en", external_id="s1"),
        sense_id=sense_id,
        lexicon="oewn:2025",
    )


def test_context_flagged_with_its_current_sense_gives_cloze_original():
    """Sin aviso: la marca la puso el usuario, y ya sabe por qué. El doble sin
    guion falla si se le llama."""
    repository = FakeRepository(
        [SOJOURNED], PAST_VERBS, DEFINITIONS, flags=frozenset({_flag("sojourn-v-1")})
    )
    generator = ScriptedDistractorGenerator([])

    item = next_exercise(repository, generator, InOrder(), choice=True)

    assert isinstance(item, ClozeExercise)
    assert isinstance(item.exercise, ClozeOriginalChoice)
    assert item.definition_fallback is None
    assert generator.requests == []


def test_flag_on_another_sense_does_not_affect_the_context():
    """La marca es del sentido que se marcó. Si el contexto tiene otro, por
    otro léxico u otra política (D-034), vuelve a dar `mcq_definition`."""
    repository = FakeRepository(
        [SOJOURNED], definitions=DEFINITIONS, flags=frozenset({_flag("sojourn-v-2")})
    )

    item = next_exercise(
        repository, ScriptedDistractorGenerator([FROM_MODEL]), InOrder(), choice=True
    )

    assert isinstance(item, DefinitionExercise)
