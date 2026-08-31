"""V2-227 scope B — the progress stream, in sentences a person can understand.

Operator, 2026-08-20: «they need to see IN REAL TIME what is happening: I enter this website, apply the filter,
launch it, get results, am browsing, am triaging». Seven minutes of blank screen is the
experience being fixed, and it is not fixed with more telemetry but with telemetry that can be read.

The raw material ALREADY existed: V2-048 gave each `tool_use` a `{where, action, target}`, so the browser layer
always knew that it was on `booking.com`. What did not reach the operator was that word — the
phase said «opening a page…» with the host right beside it. This tests the half that turns one thing into
the other, and that travels along the existing channel (B4).
"""
import pytest

from nucleo.workers import progress as P
from nucleo.workers.claude_session import _tool_phase


# ── B1: la frase nombra el SITIO y la COSA ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cmd,expected", [
    ("-m nucleo.nav_cli navigate https://www.booking.com/searchresults?ss=Sevilla", "entrando en booking.com…"),
    ("-m nucleo.nav_cli click \"Buscar\"", "pulsando «Buscar»…"),
    ("-m nucleo.nav_cli type \"Sevilla\" --submit", "escribiendo «Sevilla»…"),
    ("-m nucleo.nav_cli scroll down", "recorriendo la página…"),
    ("-m nucleo.nav_cli extract --limit 14", "recogiendo lo que hay en la página…"),
    ("-m nucleo.mem_cli recall \"el coche del operador\"", "buscando «el coche del operador» en la memoria…"),
])
def test_a_bridge_command_becomes_a_sentence(cmd, expected):
    assert _tool_phase("Bash", {"command": cmd}) == expected


def test_the_web_search_says_WHAT_it_searched():
    assert _tool_phase("WebSearch", {"query": "hoteles 4 estrellas Sevilla"}) == "buscando «hoteles 4 estrellas Sevilla»…"


def test_a_snapshot_REF_is_never_shown_to_the_operator():
    """The browser identifies elements by snapshot ref (`ref12`), which is the right way to drive the
page and the opposite of readable: «clicking «ref12»» says less than «clicking on the page» and also
shows the operator our plumbing."""
    assert _tool_phase("Bash", {"command": "-m nucleo.nav_cli click ref12"}) == "pulsando en la página…"


def test_the_url_is_reduced_to_its_HOST_even_when_it_arrives_decorated():
    """`_nav_target` returns «→ https://…»; a `host_of` that understood only a bare URL would return the
entire decoration, which is developer text the operator should never have had to read."""
    assert P.host_of("→ https://www.booking.com/searchresults?ss=Sevilla&checkin=2026-08-28") == "booking.com"
    assert P.host_of("Buscar") == "Buscar"          # the target of a click is a label, not an address


def test_hbnote_still_sets_its_OWN_phase():
    """Sensitivity, and the contract V2-048 established: the worker report is RICHER than anything
we can derive from the tool, so overwriting it with a generic phase loses information."""
    assert _tool_phase("Bash", {"command": "python -m nucleo.agent_report phase \"aplicando el filtro\""}) == ""


def test_an_unknown_tool_still_says_something():
    """Fail-open: a generic phase is worse than a specific one and much better than none — the silent card is
exactly the failure this fixes."""
    assert _tool_phase("HerramientaQueNoConocemos", {}) != ""


# ── «I launch it, get results»: the milestone requested by name ─────────────────────────────────────────────
@pytest.mark.parametrize("n,expected", [
    (12, "12 resultados en la página"), (1, "1 resultado en la página"),
    (0, "sin resultados en esta página"),
])
def test_the_outcome_of_an_extraction_is_a_phase_too(n, expected):
    assert P.found(n) == expected


def test_ZERO_is_said_out_loud():
    """Hiding it would make a page that returned nothing look exactly like one that was never read, which is the
family of silences we have been eliminating all day."""
    assert P.found(0) and "sin resultados" in P.found(0)


def test_the_browser_bridge_ACTUALLY_reports_it():
    """The half that turns it into behavior. And through the `dispatch.session_phase` gateway, the same one used by
`hbnote`: B4 says the stream travels along the existing channel, never through a parallel one.

Match the CALL and not the entire expression character by character. The first version required the literal
`_say_phase(task_id, _progress.found(len(items)))` and went red on 2026-08-20 when V2-234 switched to
counting NAMED results instead of raw rows — a change that does not affect at all what this
test says it measures (that the bridge reports, and through the existing channel). It is the same trap already paid for in
V2-222 with a V2-199 assert: a test tied to syntax turns any refactor into a false red, and
teaches people to look the other way when the red actually matters. Its own node determines what is counted (4.31).
    """
    import inspect
    import re

    from widgets.navegador import act_api
    src = inspect.getsource(act_api)
    assert re.search(r"_say_phase\(task_id,\s*_progress\.found\(", src), "el puente tiene que REPORTAR la fase"
    assert "_d.session_phase(rec.task_id, phrase)" in inspect.getsource(act_api._say_phase)


# ── B2: una fase larga tiene que decir que sigue viva ────────────────────────────────────────────────────────
def test_a_long_phase_says_how_long():
    assert P.still_alive("recorriendo la página", 95) == "recorriendo la página — lleva 1 min"
    assert P.still_alive("leyendo la página…", 20) == "leyendo la página — lleva 20s"


def test_the_heartbeat_does_NOT_rewrite_the_phase():
    """If the heartbeat stored its own text, the next one would decorate the decoration («… 1 min elapsed — 2
min elapsed»). It is EMITTED and not stored: the record retains the clean phase."""
    import time as _t

    from nucleo import dispatch as d

    class _R:
        task_id, kind, phase, status, paused = "1", "web", "recorriendo la página", "running", False
        started = last_event_at = _t.time() - 40
        trace_id = ""
    rec = _R()
    d._SESSIONS["1"] = rec
    try:
        said = d.session_alive("1")
        assert "lleva" in said
        assert rec.phase == "recorriendo la página", "el latido pisó la fase del registro"
    finally:
        d._SESSIONS.pop("1", None)


@pytest.mark.parametrize("status,paused", [("done", False), ("cancelled", False), ("running", True)])
def test_nothing_that_is_not_WORKING_beats(status, paused):
    """Sensitivity: a heartbeat from a finished task says it is still alive, which is exactly the lie this
entire day has been removing from the system. And a PAUSED task (the operator's ⏻) is not working: it does not beat."""
    import time as _t

    from nucleo import dispatch as d

    class _R:
        task_id, kind, phase, trace_id = "9", "web", "leyendo", ""
        started = last_event_at = _t.time() - 40
    rec = _R()
    rec.status, rec.paused = status, paused
    d._SESSIONS["9"] = rec
    try:
        assert d.session_alive("9") == ""
    finally:
        d._SESSIONS.pop("9", None)


def test_the_loop_beats_on_a_TIMER_not_every_tick():
    """The loop runs at ~1 Hz. Without the per-task marker it would emit a heartbeat every SECOND and drown out the channel the
heartbeat exists to make readable."""
    import inspect

    from nucleo import loop
    src = inspect.getsource(loop.Loop._supervise_workers if hasattr(loop, "Loop") else loop)
    assert "_BEAT_SECS" in src and "self._last_beat[tid] = now" in src
    assert loop._BEAT_SECS >= 5


def test_the_beat_is_forgotten_when_the_task_dies():
    """A task-indexed dictionary that nobody prunes is a leak, and this loop lives as long as the process does."""
    import inspect

    from nucleo import loop
    assert "self._last_beat = {k: v for k, v in self._last_beat.items() if k in live_ids}" in inspect.getsource(loop)


# ── the doctrine, made into a test ───────────────────────────────────────────────────────────────────────────
def test_the_phrasing_knows_about_BRIDGES_and_not_about_errands():
    """It is a RESOURCE: it must read the same for a hotel, a rocket's task list, and a house
in Los Angeles. It knows about browsers, memory, widgets, and files; nothing about errands."""
    # Check what the operator READS—the vocabulary phrases—not the entire file: the docstrings deliberately cite
    # the operator's examples (hotels, a house in Los Angeles, `ss=Sevilla` in a sample URL)
    # to say that none of them may appear in a sentence.
    said = " ".join([f(t) for table in P._SAY.values() for f in table.values() for t in ("", "X")]).lower()
    said += " " + " ".join(P._BY_WHERE.values()).lower()
    said += " " + " ".join([P.found(0), P.found(3), P.still_alive("leyendo", 30)]).lower()
    for domain in ("hotel", "restaurante", "coche", "casa", "vuelo", "wallapop", "sevilla", "booking"):
        assert domain not in said, f"«{domain}» en una frase de progreso: lo general convertido en atajo"
    # And the PLACES it knows are bridges, not errands.
    assert set(P._SAY) == {"navegador", "web", "memoria", "widget", "zaelar", "archivo", "codigo", "sistema"}
