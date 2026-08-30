#
# test_the_dedup_says_why_it_did_not_fire.py — V2-507.
#
# Only a dedup HIT was ever emitted, so a miss was mute — and «no live session matched» reads exactly like
# «there was no live session to match against». Those two want OPPOSITE fixes: a broken yardstick, or a
# session that died at birth. Measured 2026-08-30 in `cheapest-monitor__us` (round 20260830-114302): two
# result sheets opened, ONE worker ever started, no `task/dedup` row, and replaying the sandbox event log
# still could not tell which had happened. The harness reported «the dedup did not fire (containment 1.0 >=
# 0.45)» — a number it computed between the two goals IT saw, which is a different pair from the one the
# engine compares, so it could not falsify the engine's decision either.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_the_dedup_says_why_it_did_not_fire.py
#
import asyncio

import pytest

import bus
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import dispatch, matching
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec
from nucleo.workers.session import SessionRecord

_ERRAND = "Investigate work monitors available for purchase around San Francisco under 300 dollars"
_OTHER = "Reserve a table for four tonight at a restaurant in Bilbao with a terrace"
# Shares content words with _ERRAND ("investigate", "available", "around") but is a different errand: the
# case that proves `best` carries a real measurement and not a default.
_NEAR = "Investigate which coffee machines are available around Seattle for a small office"


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


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


@pytest.fixture
def fake_backend(monkeypatch):
    monkeypatch.setattr(dispatch, "get_backend", lambda *a, **k: _FakeBackend())


def _live(tid: str, goal: str, status: str = "running") -> None:
    dispatch._SESSIONS[tid] = SessionRecord(task_id=tid, kind="web", status=status, goal=goal)


# ── the rule and its evidence come from the SAME loop ────────────────────────────────────────────────────

def test_with_nothing_live_the_evidence_says_nobody_was_there(monkeypatch):
    """`live: 0` is the decisive one: no yardstick can be blamed when there was nothing to compare."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dup, ev = dispatch.dedup_scan(_ERRAND, "web")
    assert dup is None
    assert ev["live"] == 0 and ev["best"] == 0.0 and ev["against"] == "" and ev["by"] == ""


def test_a_genuine_miss_reports_the_best_it_saw_and_against_whom(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _live("live-1", _NEAR)
    dup, ev = dispatch.dedup_scan(_ERRAND, "web")
    assert dup is None
    assert ev["live"] == 1
    assert ev["against"] == "live-1"
    assert 0.0 < ev["best"] < ev["bar"], "the row must carry the number it MEASURED, not a default zero"


def test_a_comparison_that_scored_zero_still_names_who_it_compared_against(monkeypatch):
    """Zero is a RESULT, not an absence. Leaving `against` empty here would report «nobody to compare with»
    for a session that was right there — the exact confusion this whole row exists to remove."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _live("live-1", _OTHER)
    dup, ev = dispatch.dedup_scan(_ERRAND, "web")
    assert dup is None and ev["live"] == 1 and ev["against"] == "live-1" and ev["best"] == 0.0


def test_a_hit_says_which_half_decided_it(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _live("live-1", _ERRAND)
    dup, ev = dispatch.dedup_scan(_ERRAND + " and with a warranty", "web")
    assert dup == "live-1"
    assert ev["by"] == "containment" and ev["best"] >= ev["bar"]


def test_a_same_widget_hit_is_not_filed_as_a_containment_it_never_computed(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    dispatch._SESSIONS["live-1"] = SessionRecord(
        task_id="live-1", kind="code", status="running",
        goal="Implementar en el widget youtube el modo pantalla completa")
    dup, ev = dispatch.dedup_scan("cambia el widget youtube para que ordene la lista", "code")
    assert dup == "live-1" and ev["by"] == "widget"


def test_a_dead_session_is_not_something_to_compare_against(monkeypatch):
    """The hypothesis the emit exists to settle: an identical goal that is no longer LIVE is invisible, and
    a miss against it is CORRECT — which is exactly why the row has to carry `live`."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _live("dead-1", _ERRAND, status="done")
    dup, ev = dispatch.dedup_scan(_ERRAND, "web")
    assert dup is None and ev["live"] == 0


def test_the_bar_is_read_from_the_shared_primitive(monkeypatch):
    """A bar copied by hand drifts; read from its source it cannot."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _, ev = dispatch.dedup_scan(_ERRAND, "web")
    assert ev["bar"] == float(matching.SAME_ERRAND)


def test_find_duplicate_still_answers_exactly_what_it_used_to(monkeypatch):
    """The wrapper must not change a single verdict — every existing caller reads only the tid."""
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    _live("live-1", _ERRAND)
    assert dispatch.find_duplicate(_ERRAND + " and with a warranty", "web") == "live-1"
    assert dispatch.find_duplicate(_OTHER, "web") is None


# ── the WIRING: the row is emitted by the real path, not by a helper called by hand ──────────────────────

def _drive(monkeypatch, *, live: tuple[str, str] | None, request: str):
    """Publishes a real `escalate.requested` and lets `run_listener` consume it."""
    from nucleo.flash import escalate

    rows: list = []

    def _fake_emit(kind, label, **kw):
        if kind == "task" and label in ("dedup", "dedup_miss"):
            rows.append((label, kw.get("extra") or {}))
    monkeypatch.setattr("voice.observer.emit", _fake_emit)
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")

    async def run():
        bus.reset(); escalate.reset()
        dispatch._SESSIONS.clear()
        if live:
            _live(*live)
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(request, context={"kind": "web"})
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); task.cancel()

    asyncio.run(run())
    dispatch._SESSIONS.clear()
    return rows


def test_a_miss_with_nothing_live_emits_the_row_through_the_real_listener(fresh_db, fake_backend, monkeypatch):
    rows = _drive(monkeypatch, live=None, request=_ERRAND)
    assert rows, "the negative decision must leave a row — that muteness is the whole defect"
    label, extra = rows[0]
    assert label == "dedup_miss"
    assert extra["live"] == 0
    assert "ninguna tarea viva contra la que comparar" in extra["reason"]


def test_a_miss_against_a_live_errand_names_it_and_its_number(fresh_db, fake_backend, monkeypatch):
    rows = _drive(monkeypatch, live=("live-1", _OTHER), request=_ERRAND)
    assert rows and rows[0][0] == "dedup_miss"
    extra = rows[0][1]
    assert extra["live"] == 1 and extra["against"] == "live-1"
    assert 0.0 <= extra["best"] < extra["bar"]
    assert extra["model"] == "separate", "the second half ran and said separate — that has to be visible too"


def test_a_HIT_does_not_emit_a_miss(fresh_db, fake_backend, monkeypatch):
    """The other direction. Without this, «emit always» would satisfy every test above."""
    async def _noop_inject(which, msg):
        return [which]
    monkeypatch.setattr(dispatch, "inject", _noop_inject)
    rows = _drive(monkeypatch, live=("live-1", _ERRAND), request=_ERRAND + " and with a warranty")
    assert rows and [lbl for lbl, _ in rows] == ["dedup"], f"a hit must emit only `dedup`: {rows}"


def test_a_crashed_second_half_is_not_recorded_as_separate(fresh_db, fake_backend, monkeypatch):
    """The same confusion one layer in: a judge that BLEW UP used to look like one that answered «separate»."""
    from nucleo.flash import escalate

    rows: list = []

    def _fake_emit(kind, label, **kw):
        if kind == "task" and label == "dedup_miss":
            rows.append(kw.get("extra") or {})
    monkeypatch.setattr("voice.observer.emit", _fake_emit)

    def _boom(*a, **k):
        raise RuntimeError("judge unreachable")
    monkeypatch.setattr(dispatch, "about_a_live_errand", _boom)

    async def run():
        bus.reset(); escalate.reset()
        dispatch._SESSIONS.clear()
        _live("live-1", _OTHER)
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(_ERRAND, context={"kind": "web"})
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); task.cancel()

    asyncio.run(run())
    dispatch._SESSIONS.clear()
    assert rows and rows[0]["model"] == "error:RuntimeError"
    # …and the errand still ran: an unreachable judge must never block work.
