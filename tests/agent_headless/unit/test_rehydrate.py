"""
test_rehydrate.py — REHYDRATION: work left halfway through by a restart must not disappear silently.

Anchored to the 2026-08-12 incident, reconstructed event by event from the durable log:

    12:19:46  🧭 Flash → Brain Worker  «Busca en Wallapop … veleros … mínimo 45 pies»   (task 1)
    12:19:51  ui canvas (instancias): ['navegador::t1']
    12:19:52  ui canvas (instancias): ['navegador::t1', 'navegador']
    12:21:15  ── the process RESTARTS (whisper/background/homeostasis start) ──
              …and then NOTHING more is heard from the worker: no event, no ledger entry, no notification.
    12:21:23  the screen KEEPS displaying the two cards for a browser that no longer exists
    12:27:01  ui canvas (instances): []          ← the operator reloads; blank desktop

Three distinct holes, one for each block in this file:
  (1) the live-session registry was in RAM and NOBODY read it at startup → the work died without a trace;
  (2) web continuity (`native_sid`) was also in RAM → even if we wanted to, there was nothing with which to CONTINUE;
  (3) a reset must DELETE that trace: killing work by hand is an instruction, not a crash.

The decision about what gets resumed lives in `rehydrate.classify`, which is PURE — it is tested in full without a database or clock.
"""
import json
import time

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import rehydrate as R

# The REAL lost goal, verbatim from the escalation event.
VELEROS = ('Busca en Wallapop (el operador dice "Gualapop", es Wallapop) veleros en venta en España con un mínimo '
           'de 45 pies de eslora. Haz una selección de los CINCO mejores.')


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture(autouse=True)
def _widget_data_sandbox(tmp_path, monkeypatch):
    """WIDGET DATA GOES TO A TEMPORARY DIRECTORY — ALWAYS, in EVERY test in this file.

    Below is a test that calls the REAL `reset.reset_all()` (deliberately: what it verifies is the actual wiring,
    not a mock). On 2026-08-12, that `reset_all` learned to leave the surfaces BLANK
    (`widgets.reset.blank_all()`), and `blank_all` traverses `store.DATA_DIR`… which in an unisolated test is the
    operator's REAL directory. Observed live TWICE: running the suite erased the 6 sailboats a worker had just
    delivered from the screen, without leaving a single event —`blank_all` writes via
    `store.forget()` + deletion of `state.json`, not via `store.save`, so it emits no signal— and the symptom looked like
    a widget persistence bug.

    It is `autouse` and NOT optional: the protection cannot depend on the next test remembering to request it.
    A unit test has no reason whatsoever to read or touch the operator's real widget data."""
    from widgets import store as _store
    sandbox = tmp_path / "widgets_data"
    sandbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_store, "DATA_DIR", str(sandbox))
    yield sandbox


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _live(**kw) -> dict:
    base = {"id": "1", "goal": VELEROS, "kind": "web", "status": "running", "phase": "buscando"}
    base.update(kw)
    return base


# ── 1. the DECISION (pure): what continues automatically and what gets reported ─────────────────────────────
def test_a_search_cut_by_a_restart_is_resumed():
    now = time.time()
    plan = R.classify([_live()], at=now - 90, now=now)
    assert [e["id"] for e in plan["resume"]] == ["1"]
    assert plan["buried"] == []


def test_a_code_worker_is_never_resumed_on_its_own():
    """Resuming the generator REWRITES the code of an operator widget. It gets reported and remains idle."""
    now = time.time()
    plan = R.classify([_live(kind="code", goal="reescribe el widget de agenda")], at=now - 60, now=now)
    assert plan["resume"] == []
    assert "código" in plan["buried"][0]["why"]


def test_work_the_operator_paused_stays_paused():
    now = time.time()
    plan = R.classify([_live(paused=True)], at=now - 60, now=now)
    assert plan["resume"] == [] and "pausad" in plan["buried"][0]["why"]


def test_a_session_waiting_for_an_answer_is_reported_not_relaunched():
    """The question died with the process that was supporting it: relaunching the worker does not recover it."""
    now = time.time()
    plan = R.classify([_live(waiting_on="user", ask="¿te vale con 40 pies?")], at=now - 60, now=now)
    assert plan["resume"] == [] and "respuesta" in plan["buried"][0]["why"]


def test_old_work_is_reported_but_not_resumed():
    """«Search for sailboats» from hours ago is not pending work. It appears in Processes; it is not relaunched."""
    now = time.time()
    plan = R.classify([_live()], at=now - (R.STALE_S + 60), now=now)
    assert plan["resume"] == [] and plan["stale"] is True
    assert "vieja" in plan["buried"][0]["why"]


def test_a_crash_loop_stops_resurrecting_the_same_goal():
    """Anti-loop: if it has already resumed `RESUME_CAP` times and crashed again, it stops being respawned."""
    now = time.time()
    marks = {R._goal_key(VELEROS): {"n": R.RESUME_CAP, "ts": now}}
    plan = R.classify([_live()], at=now - 60, now=now, marks=marks)
    assert plan["resume"] == [] and "reanudé" in plan["buried"][0]["why"]


def test_one_restart_never_becomes_a_worker_storm():
    now = time.time()
    many = [_live(id=str(i), goal=f"tarea distinta número {i}") for i in range(R.MAX_RESUME + 4)]
    plan = R.classify(many, at=now - 60, now=now)
    assert len(plan["resume"]) == R.MAX_RESUME
    assert all("tope" in e["why"] for e in plan["buried"])


def test_finished_sessions_are_not_pending_work():
    now = time.time()
    plan = R.classify([_live(status="done"), _live(id="2", status="error")], at=now - 60, now=now)
    assert plan["resume"] == [] and plan["buried"] == []


# ── 2. the durable TRACE: without it, startup has nothing to read ───────────────────────────────────────────
def test_live_work_leaves_a_trace_with_a_timestamp(fresh_db):
    R.remember([_live()], now=1000.0)
    snap = R.snapshot()
    assert snap["at"] == 1000.0
    assert snap["sessions"][0]["goal"] == VELEROS


def test_nothing_in_flight_leaves_no_trace(fresh_db):
    R.remember([_live()])
    R.remember([_live(status="done")])          # it finished → there is nothing to rehydrate
    assert R.snapshot() is None


def test_the_trace_is_consumed_once(fresh_db):
    """If the process crashes again at startup, the SAME trace cannot resume twice."""
    R.remember([_live()])
    first = R.at_boot(schedule=False)
    assert first["found"] == 1
    assert R.at_boot(schedule=False)["found"] == 0


def test_a_clean_boot_is_a_silent_no_op(fresh_db):
    """The normal case —nothing was in flight— costs neither an event nor a line in the ledger."""
    from nucleo.workers import ledger
    out = R.at_boot(schedule=False)
    assert out == {"found": 0, "resume": [], "buried": []}
    assert ledger.history() == []


def test_interrupted_work_shows_up_in_the_operators_process_list(fresh_db):
    """What was lost must be VISIBLE (operator rule: a state that can mislead must be visible)."""
    from nucleo.workers import ledger
    R.remember([_live()])
    R.at_boot(schedule=False)
    hist = ledger.history()
    assert len(hist) == 1
    assert hist[0]["status"] == "interrumpido" and hist[0]["ok"] is False
    assert "Wallapop" in hist[0]["goal"]


def test_resuming_marks_the_goal_so_the_next_crash_gives_up(fresh_db):
    R.remember([_live()])
    R.at_boot(schedule=False, now=2000.0)
    marks = R._marks(2000.0)
    assert marks[R._goal_key(VELEROS)]["n"] == 1
    # …and after several hours the counter expires: tomorrow that goal gets its lives back.
    assert R._marks(2000.0 + R.MARK_TTL_S + 1) == {}


def test_the_events_land_in_the_brain_workers_family(fresh_db):
    """Caught live: `observer.emit` does `ev.update(extra)`, so a `kind` inside `extra` OVERRIDES the event's kind.
    These lines were classified as `code`/`web`, and the viewer's «Brain Workers» chip did not display them.
    A notification that cannot be seen is a notification that does not exist."""
    import bus
    seen = []
    sink = lambda rec: seen.append(rec["payload"]) if rec["topic"] == "observer" else None
    bus.add_sink(sink)
    try:
        R.remember([_live(), _live(id="2", kind="code", goal="reescribe el widget de agenda")])
        R.at_boot(schedule=False)
    finally:
        bus.remove_sink(sink)
    mine = [e for e in seen if isinstance(e, dict) and "reiniciar" in str(e.get("label") or "")]
    assert len(mine) == 2
    for ev in mine:
        assert ev["kind"] == "task"       # ← the FAMILY («Brain Workers»), not the type of work
        assert ev["cat"] == "worker"      # observer._CAT stamps it; passing it manually allowed a withdrawal to be fabricated
    assert {e.get("work") for e in mine} == {"web", "code"}


def test_the_resume_really_fires_and_carries_the_goal(fresh_db):
    """The plan is not enough: we must verify that re-escalation actually GOES OUT. It is deliberately deferred (the
    escalation listener must be subscribed or the event is published to nobody), so this exercises `create_task`
    and real `sleep` — the only part untouched by tests with `schedule=False`."""
    import asyncio

    from nucleo.flash import escalate

    calls = []

    async def _run():
        orig = escalate.escalate_to_slowbrain
        escalate.escalate_to_slowbrain = lambda req, context=None: calls.append((req, context or {})) or 1
        try:
            R.remember([_live()])
            out = R.at_boot(delay=0.0)          # schedule=True: creates the real task
            assert len(out["resume"]) == 1
            for _ in range(50):                 # let the deferred task run
                await asyncio.sleep(0.01)
                if calls:
                    break
        finally:
            escalate.escalate_to_slowbrain = orig

    asyncio.run(_run())
    assert len(calls) == 1
    req, ctx = calls[0]
    assert req == VELEROS                       # the complete goal, not a summary
    assert ctx["kind"] == "web" and ctx["rehydrated"] is True


def test_at_boot_reports_what_it_decided(fresh_db):
    R.remember([_live(), _live(id="2", kind="code", goal="reescribe el widget de agenda")])
    out = R.at_boot(schedule=False)
    assert out["found"] == 2
    assert [e["id"] for e in out["resume"]] == ["1"]
    assert [e["id"] for e in out["buried"]] == ["2"]


# ── 3. the dispatch seam: the trace is left by the component that already knows something changed ────────────
def test_dispatch_leaves_the_trace_when_it_projects_live_sessions(fresh_db):
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    dispatch._SESSIONS.clear()
    dispatch._last_sync = None
    try:
        rec = SessionRecord(task_id="1", goal=VELEROS, kind="web", status="running", phase="buscando")
        dispatch._SESSIONS["1"] = rec
        dispatch.sync_state()
        snap = R.snapshot()
        assert snap is not None and snap["sessions"][0]["id"] == "1"
    finally:
        dispatch._SESSIONS.clear()
        dispatch._last_sync = None


def test_web_continuity_survives_the_restart(fresh_db):
    """Without the persisted `native_sid`, «resuming» would mean starting the search from scratch."""
    from nucleo import dispatch
    dispatch._WEB_RESUME.clear()
    try:
        dispatch._WEB_RESUME["veleros wallapop"] = {"native_sid": "sess-abc", "nav_task": "t1",
                                                   "ts": time.time(), "count": 1, "goal": VELEROS}
        dispatch._resume_persist()
        dispatch._WEB_RESUME.clear()                      # ← the process dies
        assert dispatch._resume_restore() == 1            # ← and the next one recovers it
        assert dispatch._WEB_RESUME["veleros wallapop"]["native_sid"] == "sess-abc"
    finally:
        dispatch._WEB_RESUME.clear()


def test_stale_web_continuity_is_not_revived(fresh_db):
    from nucleo import dispatch
    dispatch._WEB_RESUME.clear()
    try:
        dispatch._WEB_RESUME["viejo"] = {"native_sid": "x", "ts": time.time() - (dispatch._RESUME_TTL + 60)}
        dispatch._resume_persist()
        dispatch._WEB_RESUME.clear()
        assert dispatch._resume_restore() == 0
    finally:
        dispatch._WEB_RESUME.clear()


# ── 4. a RESET is an instruction, not a crash ───────────────────────────────────────────────────────────────
def test_a_reset_does_not_let_the_next_boot_resurrect_the_work(fresh_db):
    """The operator presses Reset «to start from scratch»: the next startup must not return the work to them."""
    from nucleo import reset
    R.remember([_live()])
    reset.reset_all()
    assert R.snapshot() is None
    assert R.at_boot(schedule=False)["found"] == 0


# ── 4. RESUMING IS NOT «THAT DOESN'T WORK FOR ME, SEARCH FURTHER» ────────────────────────────────────────────
# Observed live on 2026-08-12: two unrelated consecutive restarts, midway through a sailboat investigation, turned
# it into «ROUND 2 of an already-known investigation (≥80 candidates)». Round expansion is correct when the OPERATOR
# asks for the same thing again (meaning the response was not useful); applied to a CRASH, it makes the request
# more demanding precisely when it needs to be resumed, and with the same clock.
def test_a_crash_resume_inherits_the_brief_instead_of_opening_a_harder_round(fresh_db):
    import asyncio

    from nucleo.flash import escalate

    calls = []

    async def _run():
        orig = escalate.escalate_to_slowbrain
        escalate.escalate_to_slowbrain = lambda req, context=None: calls.append((req, context or {})) or 1
        try:
            R.remember([_live(id="7")])
            R.at_boot(delay=0.0)
            for _ in range(50):
                await asyncio.sleep(0.01)
                if calls:
                    break
        finally:
            escalate.escalate_to_slowbrain = orig

    asyncio.run(_run())
    _, ctx = calls[0]
    # The ALREADY-INTENDED path for this: `_compose_brief` reuses the brief unchanged when its originating task arrives
    assert ctx["resume"]["brief_task"] == "7", "sin el brief de origen, el objetivo casa por parecido y EXPANDE"


def test_the_brief_of_the_dead_task_is_the_one_reused(fresh_db):
    """The complete seam: the brief saved by the dead task is the one picked up on resumption — same round,
    same breadth, same criteria. Changing criteria halfway through a search that the operator believes is
    following the same script is worse than starting from scratch."""
    import asyncio

    from nucleo import dispatch, research

    brief = {"goal": "veleros de 42 a 49 pies hasta 50.000 €", "hard": ["≤ 50.000 €"], "round": 1,
             "breadth": {"min_candidates": 40, "angles": []}, "deliverable": {"widget": "results", "n_final": 10}}
    research.save("7", brief)
    research.remember_round(dispatch._goal_key(VELEROS), brief)   # the bait that triggered round 2

    out = asyncio.run(dispatch._compose_brief(VELEROS, "", True, {"brief_task": "7"}))
    assert out["round"] == 1, f"reanudar no sube de ronda (salió {out.get('round')})"
    assert (out["breadth"] or {})["min_candidates"] == 40, "ni endurece la amplitud"
    assert out["deliverable"]["n_final"] == 10


def test_a_reset_in_a_test_never_touches_the_operators_real_widget_data(tmp_path, monkeypatch):
    """The damage already done, turned into a guard. `reset_all` blanks the surfaces by traversing
    `store.DATA_DIR`; if a test calls it without isolating that directory, it deletes the operator's REAL data —
    silently, because `blank_all` does not go through `store.save` and therefore emits no signal. Verified live:
    two runs of this suite emptied the sheet containing the 6 sailboats a worker had just delivered."""
    from widgets import reset as wreset
    from widgets import store as _store

    real = _store.DATA_DIR                       # the real one, resolved BEFORE isolation
    sandbox = tmp_path / "solo_esto_se_toca"
    (sandbox / "results").mkdir(parents=True)
    (sandbox / "results" / "state.json").write_text('{"items": [{"title": "un velero"}]}', encoding="utf-8")
    monkeypatch.setattr(_store, "DATA_DIR", str(sandbox))

    out = wreset.blank_all()
    assert "results" in out["blanked"]
    # `results` declares `blank()`, so the sheet is REWRITTEN empty instead of the file being deleted
    kept = json.loads((sandbox / "results" / "state.json").read_text(encoding="utf-8"))
    assert not (kept.get("items") or []), "en el sandbox SÍ deja la hoja en blanco"
    assert str(sandbox) != real, "y el sandbox no puede ser el directorio real"
