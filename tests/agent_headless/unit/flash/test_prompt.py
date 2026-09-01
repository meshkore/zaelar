"""Tests for nucleo/flash/prompt.py (V2-004 · T67) — the FlashBrain prompt composes its own MEMORY (state+query)."""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import memory_cache, prompt


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    memory_cache.reset()   # the session cache (T114) is global; start clean for each test
    yield
    memory_cache.reset()
    memdb.reset_db()


def test_prompt_injects_operator_from_state(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo, sin narrar"})
    system, _ids = prompt.build_flash_system()
    assert "Ricart" in system
    assert "directo, sin narrar" in system
    # V2-027: the composed STATE contains the MISSION (WHO YOU ARE) + the situational context (WHO YOU HAVE IN FRONT OF YOU)
    assert "QUIÉN ERES" in system
    assert "QUIÉN TIENES DELANTE" in system
    # the language lock and the CONCISE resource layer are always present
    assert "IDIOMA" in system
    assert "widget_data" in system and "web_search" in system


def test_prompt_recall_pulls_relevant_memory(fresh_db):
    memapi.write_now("el coche del operador está en el taller hasta el viernes", kind="fact", level="long")
    system, ids = prompt.build_flash_system(recall_query="¿dónde está mi coche?")
    assert "taller" in system
    assert ids            # returned IDs of memory entries used (for reinforcement/logging)


def test_prompt_empty_memory_no_crash(fresh_db):
    system, ids = prompt.build_flash_system(recall_query="hola")
    assert isinstance(system, str) and "IDIOMA" in system
    assert ids == []      # no memories → no IDs


def test_directive_block(fresh_db):
    system, _ = prompt.build_flash_system(directive="tutéame y sé breve")
    assert "tutéame y sé breve" in system
    assert "INSTRUCCIÓN DE ESTILO ACTIVA" in system


@pytest.mark.parametrize("text", [
    "where is my car",
    "where's my car?",
    "¿dónde está mi coche?",
    "do you remember what I told you?",
    "¿te acuerdas de mi cita del dentista?",
    "what did I tell you about the meeting",
    "recuérdame qué dije de la reunión",   # 'what I said about'
])
def test_needs_recall_true(text):
    assert prompt.needs_recall(text) is True


@pytest.mark.parametrize("text", [
    "hola, buenos días",
    "¿qué tal estás?",
    "let's talk about my weekend plans",
    "show me the clock please",
    "cuéntame un chiste",
    "¿me pones el tiempo en pantalla?",
])
def test_needs_recall_false(text):
    assert prompt.needs_recall(text) is False


@pytest.mark.parametrize("lang,needle", [("es", "corto o largo plazo"), ("en", "short/long-term memory")])
def test_prompt_never_exposes_memory_layers(fresh_db, monkeypatch, lang, needle):
    """The FlashBrain must NEVER talk to the operator about its internal layers ('short/long-term memory').
    Hard rule after the live bug on 2026-07-10; in V2-027 it lives in the seeded MISSION (langs), not in a static
    `_FAST_RULES` — that way the assembled prompt continues to carry it.

    The LANGUAGE is fixed, and BOTH are checked: the prohibition lives in the mission, which is PER LANGUAGE, so
    inheriting the ambient language made this test pass on the operator's machine (Spanish in its config) and
    fail anywhere else and in CI — even though nothing was wrong with the product. Checking only Spanish
    left unguarded the very language with which the product STARTS as of 2026-08-09: if the prohibition
    dropped out of English, nobody would notice."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    system, _ = prompt.build_flash_system()
    assert needle in system                  # appears ONLY in the mission's prohibition


# ── proactivity and multi-intent (use cases from 2026-08-18) ─────────────────────────────────────────
def test_the_cron_line_makes_a_spoken_reminder_insufficient():
    """V2-121 · `remember-and-remind-deadline`. Saying «I'll remind you» does not schedule anything; the prompt has to
    say it explicitly, because the run measured three turns claiming it was scheduled with zero
    mechanism behind it."""
    line = prompt._cron_line()
    assert "[[cron.create]]" in line
    assert "EN ESE TURNO" in line
    assert "YYYY-MM-DD HH:MM" in line       # the format that makes a one-time reminder EXPRESSIBLE
    assert "add_meeting" in line            # noting it down and reminding are two different things, and both are requested


def test_live_state_lists_the_next_seven_days_with_their_dates():
    """Translating «Wednesday» into an absolute date must be a READ, not mental arithmetic: a wrongly dated reminder
    is not noticed until the day it fails to sound."""
    import time as _t
    live = prompt.live_state()
    assert "Próximos días" in live
    for i in (1, 3, 7):
        assert _t.strftime("%Y-%m-%d", _t.localtime(_t.time() + i * 86400)) in live


def test_the_one_thing_per_turn_rule_is_about_actions_not_answers(fresh_db):
    """V2-120 · `quick-fact-opening-hours`. «ONE thing per turn» was read as permission to answer half a
    question: the time AND the price were requested in the same sentence, and only one half came back, two rounds in a row."""
    system, _ = prompt.build_flash_system()
    assert "UNA ACCIÓN por turno" in system
    assert "las contestas LAS DOS en ese turno" in system


def test_a_background_task_with_no_reported_step_says_so(monkeypatch):
    """V2-133 — the cross-cutting pattern: 8 of 12 cases NARRATED a phase that did not exist («it is in the
    login phase» for a gym whose name it did not yet have). The block simply asked it to «state the concrete STEP»,
    and without a reported step the model filled the gap. Now the absence is stated, and narration is prohibited with examples."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "renovar la cuota del gimnasio", "secs": 63, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": ""}])
    live = prompt.live_state()
    assert "SIN paso reportado aún" in live.split("Si el operador pregunta")[0]
    assert "JAMÁS te inventes en qué punto va" in live


def test_a_background_task_that_DID_report_a_step_still_shows_it(monkeypatch):
    """The marker is for the gap, not for the entire task: a real phase is still stated as is."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "buscar monitores", "secs": 63, "phase": "conduciendo el navegador",
         "pct": -1, "done": 0, "total": 0, "note": ""}])
    # The marker is looked for in the task LIST, not in the instruction paragraph (which cites it to explain it).
    tareas = prompt.live_state().split("Si el operador pregunta")[0]
    assert "conduciendo el navegador" in tareas
    assert "SIN paso reportado aún" not in tareas


def test_the_prompt_forbids_narrating_work_that_is_not_running(fresh_db):
    """The other half of V2-133: with NO background task there is nothing running, and the correct response
    when information is missing or something cannot be done is to say so — the criterion for those cases explicitly rewards it."""
    system, _ = prompt.build_flash_system()
    assert "NO NARRES trabajo que no está pasando" in system
    assert "PÍDELO" in system


# ── an operator detail that is NOT in their STATE (V2-127, 2026-08-18) ───────────────────────────────────
def test_the_missing_location_is_NAMED_not_left_blank(tmp_path, monkeypatch):
    """`reorder-prescription__es` ended up asking about «the exact area of Soria» — a city the operator
    had not named. Verified with a fresh DB: `state.read()["location"] is None`, meaning the state did not
    authorize naming any city. The silent gap was filled, just like the unreported worker phase."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "vacia.db"))
    from memory import db as memdb
    memdb.reset_db(); memdb.get_db()
    try:
        live = prompt.live_state()
        assert "NO SABES dónde vive el operador" in live
        assert "no supongas ninguna ciudad" in live
    finally:
        memdb.reset_db()


def test_a_known_location_costs_nothing(fresh_db):
    """The line is for the ABSENCE: with a location in the state it does not appear (the prompt does not grow because of it)."""
    from memory import api as memory
    memory.set_state({"location": "Soria, Castilla y León"})
    assert "NO SABES dónde vive el operador" not in prompt.live_state()


def test_web_search_no_longer_orders_using_a_city_that_may_not_exist(fresh_db):
    """The clause ordered it to use «the operator's CURRENT city» without considering that their state might not contain one."""
    system, _ = prompt.build_flash_system()
    assert "si su estado NO dice dónde vive, no te la inventes" in system


def test_a_concrete_fact_about_the_operator_comes_from_state_or_is_asked(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "o está en tu ESTADO o NO LO SABES" in system


def test_the_prompt_names_the_invented_jargon_and_offers_a_sanctioned_phrase(fresh_db):
    """V2-129 · turn 1: «I need to ESCALATE this to the real OPERATIONS TEAM… not in a LOCAL WIDGET» — three
    internal concepts in the first sentence the operator hears. The rule already prohibited «escalate», but the model
    invents synonyms for what it cannot name otherwise, so it is now given the sanctioned phrase."""
    system, _ = prompt.build_flash_system()
    assert "«equipo de operaciones»" in system
    assert "«widget local»" in system
    assert "me pongo con ello" in system


def test_the_background_task_list_states_what_it_is_NOT_for(monkeypatch):
    """V2-130 `book-barber-slot`. Asked which hairdresser he always goes to, the brain had nothing on
    hairdressers and answered with the background-task list instead: «I have several pending tasks for you:
    book a table at Casa Lucio, renew the gym membership…». Real items, real list, wrong KIND of thing —
    a list in context becomes an answer when the model has a hole, and the block never stated its scope."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "reservar mesa en Casa Lucio", "secs": 63, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": ""}])
    live = prompt.live_state()
    assert "TRABAJO EN CURSO" in live
    assert "estas tareas NO son candidatas" in live


def test_a_stalled_background_task_is_named_as_stalled(monkeypatch):
    """V2-131 `book-hotel-night-known`. Six turns of «it is still in progress» over a task that had emitted nothing.
    The loop's supervisor DID know it was stalled (`silent_s`, same threshold) and said so on its own — the
    prompt never got the number, so the brain could only see «it started N seconds ago» and had to guess what
    counts as too long. State the fact, same remedy as «SIN paso reportado aún»."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "reservar noche en el Hotel Palacio de la Merced", "secs": 400, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": "", "silent_s": 400}])
    tareas = prompt.live_state().split("Si el operador pregunta")[0]
    assert "ENCALLADA" in tareas
    assert "6 min SIN DAR NINGUNA SEÑAL" in tareas


def test_a_task_that_is_emitting_is_NOT_called_stalled(monkeypatch):
    """The marker is for silence, not for elapsed time: a task working and reporting stays unmarked."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "buscar monitores", "secs": 400, "phase": "conduciendo el navegador",
         "pct": -1, "done": 0, "total": 0, "note": "", "silent_s": 3}])
    tareas = prompt.live_state().split("Si el operador pregunta")[0]
    assert "conduciendo el navegador" in tareas
    assert "ENCALLADA" not in tareas


def test_the_prompt_forbids_answering_a_concrete_question_with_process(monkeypatch):
    """«Is there availability or not?» got «the process is still in progress» — which was also false. The honest answer
    is that it is not known yet, and since when there has been no signal. The rule travels WITH the task list
    (it is about what to do with it), so it only exists when there is something running — which is exactly
    when the operator asks."""
    from nucleo import dispatch as _disp
    monkeypatch.setattr(_disp, "pending_summaries", lambda: [
        {"id": "9", "request": "reservar hotel", "secs": 400, "phase": "",
         "pct": -1, "done": 0, "total": 0, "note": "", "silent_s": 400}])
    live = prompt.live_state()
    assert "TODAVÍA NO LO SABES" in live
    assert "no digas que algo «se está demorando»" in live


def test_the_prompt_forbids_handing_the_task_back_to_the_operator(fresh_db):
    """V2-132 · turn 8, after four rounds with nothing to say: «All right, I'll leave you working. Let me know when
    you have something.» With no material of its own the model MIRRORED the interlocutor's last frame and handed the
    task back to whoever had asked for it. Named explicitly, with the phrase to use instead."""
    system, _ = prompt.build_flash_system()
    assert "El trabajo es TUYO" in system
    assert "avísame cuando tengas algo" in system
    assert "sigo sin novedades" in system


# ── a criterion the model cannot VERIFY is never delivered as fulfilled (V2-469, 2026-08-28) ─────────────
def test_an_unverifiable_criterion_is_never_given_as_fulfilled(fresh_db):
    """Measured three times in `find-videos-on-a-topic-no-ai-slop` (09:52, 22:11, 22:31): the operator asked
    for videos «without AI», the model said «I'll avoid those that smell like AI» and then presented candidates as if the
    filter were resolved — no signal named, no disclaimer. The case's own criterion says both honest paths:
    name the signals you approximate with, or say you cannot guarantee it. General by design (⭐ rule: never
    wire the use case): the same shape covers «that it be trustworthy», «gluten-free», «that it have good reviews»."""
    system, _ = prompt.build_flash_system()
    assert "no puedes VERIFICAR" in system
    assert "no lo des nunca por CUMPLIDO" in system


def test_the_days_list_is_a_translator_not_a_calendar_limit():
    """V2-473 round 4: the 7-day list («Upcoming days…») ends ~Sept 5 and the model told the operator
    «in my list of upcoming days I only have through the 5th», refusing a valid Sept 8 appointment and then
    asking «is it 2026?». The list exists to translate a NAMED weekday to its date; an explicit date is
    used as given, any distance into the future, current year unless passed."""
    txt = prompt.live_state()
    assert "Próximos días" in txt
    assert "NO es el límite" in txt, "the line must state the boundary of its own purpose"
    assert "año en curso" in txt, "a dated request without a year is this year, not a question"


def test_the_stable_resources_layer_precedes_every_per_turn_block(fresh_db):
    """STABLE PREFIX FIRST (2026-09-01). The resources layer (~73% of the system chars, and the part that does
    NOT change turn to turn) goes BEFORE the per-turn blocks (state with the conversation synthesis, recall),
    and the live state stays LAST. That order is what lets the provider's prefix cache cover the bulk of the
    prompt: measured with the real blocks, the shared prefix between two consecutive turns went from 16.8% to
    97.1% of the prompt. Routing was gated by the node 2.13 bench the same day (V2-097 rule) — whoever reverts
    this order pays the prefill of ~10k tokens on every turn again."""
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo"})
    system, _ = prompt.build_flash_system(recall_block="· puede que venga a cuento: el coche es un Range Rover")
    i_how = system.find("── CÓMO OPERAS")
    i_res = system.find("── QUÉ TIENES (recursos) ──")
    i_state = system.find("QUIÉN ERES")
    i_recall = system.find("Range Rover")
    i_live = system.find("── AHORA MISMO ──")
    assert -1 not in (i_how, i_res, i_state, i_recall, i_live)
    assert i_how < i_state and i_res < i_state, "the resources layer must precede the per-turn state block"
    assert i_state < i_recall < i_live, "per-turn blocks in the volatile tail, live state last"
    assert system.rstrip().endswith("Atiende ahora la petición del operador que viene a continuación.")
