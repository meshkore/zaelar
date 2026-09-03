"""V2-570 — a DELIVERED hunt is not re-hunted in parallel: the linear gate and the inherited box.

Measured on the operator's own session (9dcff6f5, 2026-09-03, the catamaran errand): the listing fast pass
delivered 20 rows into a sheet, and seven seconds later — the sentence now complete — the model escalated the
SAME hunt to a Brain Worker. `dedup_miss` said `live: 0` (a fast pass is not a session), the worker opened a
SECOND sheet beside the first, and the operator watched two parallel processes for one errand — the exact
thing his doctrine forbids: a search resolves LINEARLY, the fast delivery IS the answer, and deeper machinery
runs only when the module judges it or the operator pushes again.

The strings below are the session's own: the fragment the fast pass ran on, and the model's escalation brief.
The wiring tests walk the REAL path (bus → `run_listener`) — V2-199's lesson: a test that never walks the
real path proves the code compiles, not that it works.

Run: .venv/bin/pytest tests/agent_headless/unit/test_a_delivered_hunt_is_not_rehunted_in_parallel.py
"""
from __future__ import annotations

import asyncio
import time

import pytest

import bus
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import dispatch, errand_continuity
from nucleo.workers import ended
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec

# The session's own strings: what the fast pass ran on, and what the model escalated seven seconds later.
_DELIVERY_GOAL = "Búscame si hay empresas de alquiler de catamaranes en plan"
_ESCALATION = ("Buscar empresas de alquiler de catamaranes de unos 45 pies en la costa mediterránea "
               "española, en la zona de Barcelona, Tarragona y Valencia. El operador quiere ver qué se "
               "alquila y a qué precios.")
_UNRELATED = "Organízame una investigación sobre la cultura griega del siglo II antes de Cristo"
_SHEET = "results--catatest"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    ended._LISTING_DELIVERIES.clear()
    ended._ENDED_SESSIONS.clear()
    dispatch._SESSIONS.clear()
    yield
    ended._LISTING_DELIVERIES.clear()
    ended._ENDED_SESSIONS.clear()
    dispatch._SESSIONS.clear()
    memdb.reset_db()
    mememb.reset()


class _FakeBackend(WorkerBackend):
    name = "fake"

    def __init__(self):
        self._alive = False
        self._spec: WorkerSpec | None = None

    async def start(self, prompt: str, *, spec: WorkerSpec) -> None:
        self._spec, self._alive = spec, True

    async def send(self, text: str) -> None:
        pass

    async def events(self):
        tid = self._spec.task_id if self._spec else ""
        yield WorkerEvent(task_id=tid, type="spawned", backend=self.name)
        yield WorkerEvent(task_id=tid, type="result", backend=self.name,
                          data={"summary": "done", "ok": True})
        self._alive = False
        yield WorkerEvent(task_id=tid, type="done", backend=self.name)

    async def stop(self, *, grace: float = 3.0) -> None:
        self._alive = False

    @property
    def alive(self) -> bool:
        return self._alive

    def native_session_id(self) -> str:
        return ""


# ── the delivery store: a fast-pass delivery is a fact with a TTL ────────────────────────────────────────

def test_a_delivery_is_recorded_and_expires_with_the_ended_window():
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    rows = ended.recent_listing_deliveries()
    assert len(rows) == 1
    assert rows[0]["goal"] == _DELIVERY_GOAL and rows[0]["sheet"] == _SHEET and rows[0]["n"] == 20
    # expired → gone from the pool the matcher reads
    ended._LISTING_DELIVERIES[f"listing:{_SHEET}"]["at"] = time.time() - ended.JUST_ENDED_S - 1
    assert ended.recent_listing_deliveries() == []


def test_the_refinement_is_consumed_exactly_once_and_a_new_delivery_rearms_it():
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    assert ended.consume_listing_refinement(f"listing:{_SHEET}") is True
    assert ended.consume_listing_refinement(f"listing:{_SHEET}") is False
    # a delivered re-run records again, which re-arms the gate: each redirect needs a fresh operator push
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=8)
    assert ended.consume_listing_refinement(f"listing:{_SHEET}") is True


def test_the_pool_hands_out_copies_never_the_store_rows():
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    ended.recent_listing_deliveries()[0]["refined"] = True
    assert ended.consume_listing_refinement(f"listing:{_SHEET}") is True, \
        "mutating a pool row must not consume the store's refinement"


# ── the decision, called directly: what inherits, what redirects, what neither ───────────────────────────

def _decide(request: str, kind: str = "generic"):
    reruns: list = []

    async def run():
        # inside a running loop so the gate can create its rerun task; the stub keeps it inert
        out = errand_continuity.inherit_and_maybe_rerun(request, kind, {}, "t-1")
        await asyncio.sleep(0.05)      # let a scheduled rerun task run against the stub and finish
        return out

    import nucleo.flash.listing_turn as LT
    orig = LT.run
    LT.run = lambda *a, **k: reruns.append((a, k)) or {"delivered": False, "n": 0, "ctx": "", "sheet": ""}
    try:
        ctx, redirected = asyncio.run(run())
    finally:
        LT.run = orig
    return ctx, redirected


def test_the_same_hunt_inherits_the_box_and_is_redirected():
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    ctx, redirected = _decide(_ESCALATION)
    assert ctx.get("sheet") == _SHEET, "the escalation must continue in the box the operator is looking at"
    assert redirected is True


def test_an_acting_kind_is_never_redirected_but_still_keeps_the_box():
    """Booking or acting on a site is a different errand even when its words contain the hunt's: the gate
    steps aside and the worker runs — writing into the SAME sheet, never a second one."""
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    ctx, redirected = _decide(_ESCALATION, kind="web")
    assert redirected is False
    assert ctx.get("sheet") == _SHEET


def test_an_unrelated_errand_neither_inherits_nor_redirects():
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    ctx, redirected = _decide(_UNRELATED)
    assert redirected is False and not ctx.get("sheet")


def test_an_escalation_that_declared_its_own_box_is_left_alone():
    """`listing_turn.run`'s own auto-escalation already carries its sheet — re-deciding it here would be a
    second yardstick, and it is also what makes the redirect→insufficient→worker chain loop-free."""
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    ctx, redirected = errand_continuity.inherit_and_maybe_rerun(
        _ESCALATION, "generic", {"sheet": "results--mine"}, "t-1")
    assert redirected is False and ctx.get("sheet") == "results--mine"


# ── the WIRING: through the real bus and the real listener (V2-199) ─────────────────────────────────────

def _drive(monkeypatch, request: str, *, deliveries: list | None = None, consume: bool = False):
    from nucleo.flash import escalate

    events: list = []
    reruns: list = []

    def _fake_emit(kind, label, **kw):
        if kind == "task":
            events.append((label, kw.get("extra") or {}))
    monkeypatch.setattr("voice.observer.emit", _fake_emit)
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")
    monkeypatch.setattr(dispatch, "get_backend", lambda *a, **k: _FakeBackend())
    monkeypatch.setattr(dispatch, "_name_errand", lambda rec: None)
    monkeypatch.setattr("nucleo.flash.listing_turn.run",
                        lambda *a, **k: reruns.append({"args": a, "kw": k})
                        or {"delivered": True, "n": 5, "ctx": "· fila", "sheet": k.get("sheet", "")})

    spawned: dict = {}

    # Capture at the SPAWN, not by sampling `_SESSIONS`: a fake session finishes in milliseconds and
    # `_run_session` pops its record in its `finally` (the very fact V2-199 was about), so any poll races it.
    orig_run_session = dispatch._run_session

    async def _capturing_run_session(task):
        rec = dispatch._SESSIONS.get(task.id)
        spawned[task.id] = getattr(rec, "sheet", "")
        return await orig_run_session(task)
    monkeypatch.setattr(dispatch, "_run_session", _capturing_run_session)

    async def run():
        bus.reset()
        escalate.reset()
        dispatch._SESSIONS.clear()
        for d in (deliveries or []):
            ended.note_listing_delivery(d["goal"], d["sheet"], n=d.get("n", 5))
            if consume:
                ended.consume_listing_refinement(f"listing:{d['sheet']}")
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(request)
        await asyncio.sleep(0.3)
        stop.set()
        await asyncio.sleep(0.05)
        task.cancel()

    asyncio.run(run())
    dispatch._SESSIONS.clear()
    return events, reruns, spawned


def test_the_first_escalation_of_a_delivered_hunt_reruns_fast_instead_of_spawning(monkeypatch):
    events, reruns, spawned = _drive(
        monkeypatch, _ESCALATION, deliveries=[{"goal": _DELIVERY_GOAL, "sheet": _SHEET, "n": 20}])
    assert spawned == {}, "the linear gate must not open a worker session for a just-delivered hunt"
    assert len(reruns) == 1, "the refined fast re-run is the errand's next step"
    assert reruns[0]["kw"].get("sheet") == _SHEET, "the re-run writes into the inherited box"
    labels = [l for l, _ in events]
    assert "linear_rerun" in labels and "sheet_inherited" in labels


def test_the_second_push_spawns_a_worker_that_keeps_the_box(monkeypatch):
    events, reruns, spawned = _drive(
        monkeypatch, _ESCALATION,
        deliveries=[{"goal": _DELIVERY_GOAL, "sheet": _SHEET, "n": 20}], consume=True)
    assert reruns == [], "the single refinement was already spent: no second redirect"
    assert list(spawned.values()) == [_SHEET], "a second push goes to the worker, but in the SAME box"


def test_a_fresh_unrelated_errand_still_spawns_normally(monkeypatch):
    """Continuity must never drop an escalation: with a delivery on record, an unrelated errand keeps its
    own life — a session of its own, no inherited sheet, no redirect."""
    events, reruns, spawned = _drive(
        monkeypatch, _UNRELATED, deliveries=[{"goal": _DELIVERY_GOAL, "sheet": _SHEET, "n": 20}])
    assert len(spawned) == 1 and reruns == []
    assert list(spawned.values()) == [""], "an unrelated errand must not inherit the delivery's box"


# ── the re-run announces its delivery by PUSHED note (the route that arrives 3/3, V2-222) ───────────────

def test_a_delivered_rerun_pushes_a_note_naming_the_rows(monkeypatch):
    pushed: list = []
    monkeypatch.setattr("voice.brain_notes.push", lambda text: pushed.append(text))
    monkeypatch.setattr("nucleo.flash.listing_turn.run",
                        lambda *a, **k: {"delivered": True, "n": 4,
                                         "ctx": "· Catamarán Bali 4.6 — 1.500 EUR", "sheet": _SHEET})
    asyncio.run(errand_continuity._rerun(_ESCALATION, _SHEET))
    assert len(pushed) == 1
    assert "Catamarán Bali" in pushed[0] and "[SISTEMA]" in pushed[0]
    assert "no digas que sigues buscando" in pushed[0]


def test_an_insufficient_rerun_pushes_nothing_the_escalation_speaks_for_itself(monkeypatch):
    pushed: list = []
    monkeypatch.setattr("voice.brain_notes.push", lambda text: pushed.append(text))
    monkeypatch.setattr("nucleo.flash.listing_turn.run",
                        lambda *a, **k: {"delivered": False, "n": 0, "ctx": "", "sheet": _SHEET,
                                         "escalated": 9})
    asyncio.run(errand_continuity._rerun(_ESCALATION, _SHEET))
    assert pushed == []


# ── the PROMPT carries the fact with its instruction (V2-453) ────────────────────────────────────────────

def test_the_prompt_names_the_delivery_and_the_linear_rule():
    from nucleo.flash import prompt as P
    ended.note_listing_delivery(_DELIVERY_GOAL, _SHEET, n=20)
    st = P.live_state()
    assert "BÚSQUEDA DE ANUNCIOS YA HECHA" in st
    assert "search_listings" in st and "escalate_to_slowbrain" in st
    assert "catamaranes" in st, "the line must name WHICH hunt was delivered (V2-193)"


def test_without_a_fresh_delivery_the_prompt_is_untouched():
    from nucleo.flash import prompt as P
    assert "BÚSQUEDA DE ANUNCIOS YA HECHA" not in P.live_state()
