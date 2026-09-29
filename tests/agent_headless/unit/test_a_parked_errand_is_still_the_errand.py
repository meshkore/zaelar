#
# test_a_parked_errand_is_still_the_errand.py — 2026-09-29, session 81095d8d.
#
# The confirm gate parks an errand and POPS its session record. The dedup compares only against `queued|running`,
# so every repetition of the order read `dedup_miss live:0` and opened ANOTHER task:
#
#     18:28:25  «i want to buy Through the Moon (2020), gime the amazon link»   → task 3, parked, question spoken
#     18:28:40  (the same text, second door)                                    → task 4, parked, question spoken
#     18:29:14  «provide the link to the product where I can buy it»           → task 5, parked, question spoken
#     18:29:40  «give me the link and don't ask me again»                      → read as a NO; task 5 discarded
#     18:29:48  «Give me the link now»                                          → task 6
#
# Four result boxes on his screen, one intention. A task waiting on him is not dead: it is the errand he is still
# talking about, and the dedup has to see it. A hit against a parked errand is FOLDED into it (the refinement
# travels with the «yes») and the brain is told which question is still waiting.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/test_a_parked_errand_is_still_the_errand.py
#
import asyncio

import pytest

import bus
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import dispatch
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec

HIS_WORDS = "i want to buy Through the Moon (2020), gime the amazon link"
REPEAT = ('Find the Amazon listing where Richard can BUY the book "Through the Moon (2020)" — and give him the '
          "direct product link. He wants the URL of the product page where he can buy it.")
OTHER = "Reserve a table for four tonight at a restaurant in Bilbao with a terrace"


class _Task:
    def __init__(self, kind="web", trusted=True, context=None):
        self.kind, self.trusted, self.context = kind, trusted, dict(context or {})


@pytest.fixture(autouse=True)
def _clean():
    dispatch._PENDING_CONFIRM.clear()
    yield
    dispatch._PENDING_CONFIRM.clear()


# ── the registry side ────────────────────────────────────────────────────────────────────────────────────

def test_a_parked_errand_is_listed_in_the_dedup_shape():
    dispatch.remember_confirm("3", HIS_WORDS, _Task())
    assert dispatch.parked_errands() == [("3", HIS_WORDS)]


def test_a_refinement_is_folded_in_and_returns_the_waiting_question():
    dispatch.remember_confirm("3", HIS_WORDS, _Task())
    q = dispatch.absorb_refinement("3", "provide the link to the product where I can buy it")
    assert q == dispatch.pending_confirm()["question"]
    assert dispatch.pending_confirm()["refinements"] == ["provide the link to the product where I can buy it"]


def test_the_yes_carries_the_refinements_with_the_errand(monkeypatch):
    seen: list = []
    from nucleo.flash import escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda request, context=None, **k: seen.append(request))
    dispatch.remember_confirm("3", HIS_WORDS, _Task())
    dispatch.absorb_refinement("3", "the original edition, shipped to Spain")
    dispatch.resolve_confirm(True)
    assert seen and HIS_WORDS in seen[0] and "shipped to Spain" in seen[0]


def test_absorbing_refreshes_the_clock():
    """Repeating the order is the opposite of forgetting it: the ask must not expire under a still-talking
    operator (V2-190's lesson, the other way round)."""
    dispatch.remember_confirm("3", HIS_WORDS, _Task())
    dispatch._PENDING_CONFIRM["3"]["ts"] -= dispatch._CONFIRM_TTL - 5
    dispatch.absorb_refinement("3", "give me the link now")
    dispatch._sweep_confirm()
    assert dispatch.pending_confirm() is not None


def test_nothing_parked_under_that_id_absorbs_nothing():
    assert dispatch.absorb_refinement("nope", "x") == ""


# ── the WIRING: the real listener, a real `escalate.requested` ───────────────────────────────────────────

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
        yield WorkerEvent(task_id=tid, type="result", backend=self.name, data={"summary": "done", "ok": True})
        self._alive = False
        yield WorkerEvent(task_id=tid, type="done", backend=self.name)

    async def stop(self, *, grace: float = 3.0) -> None:
        self._alive = False

    @property
    def alive(self) -> bool:
        return self._alive

    def native_session_id(self) -> str:
        return ""


def _drive(monkeypatch, *, parked: tuple[str, str] | None, request: str, context: dict | None = None):
    from nucleo.flash import escalate
    from voice import brain_notes

    rows: list = []

    def _fake_emit(kind, label, **kw):
        if kind == "task" and label in ("dedup", "dedup_miss"):
            rows.append((label, kw.get("extra") or {}))
    monkeypatch.setattr("voice.observer.emit", _fake_emit)
    monkeypatch.setattr(dispatch, "get_backend", lambda *a, **k: _FakeBackend())
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")
    brain_notes.drain()

    async def run():
        bus.reset(); escalate.reset()
        dispatch._SESSIONS.clear()
        if parked:
            dispatch.remember_confirm(parked[0], parked[1], _Task())
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(request, context={"kind": "web", **(context or {})})
        await asyncio.sleep(0.3)
        stop.set(); await asyncio.sleep(0.05); task.cancel()

    asyncio.run(run())
    dispatch._SESSIONS.clear()
    return rows, brain_notes.drain()


def test_a_repeat_of_a_parked_errand_opens_no_second_task(fresh_db, monkeypatch):
    rows, notes = _drive(monkeypatch, parked=("3", HIS_WORDS), request=REPEAT)
    assert rows and rows[0][0] == "dedup", f"the repeat must be absorbed, not missed: {rows}"
    assert rows[0][1]["by"] == "parked" and rows[0][1]["id"] == "3"
    assert dispatch.pending_confirm()["refinements"] == [REPEAT]
    assert any("aparcada" in n for n in notes), "the brain must be told which question is still waiting"
    assert not dispatch._SESSIONS, "no session may have been opened for the repeat"


def test_a_different_errand_still_opens(fresh_db, monkeypatch):
    rows, _ = _drive(monkeypatch, parked=("3", HIS_WORDS), request=OTHER)
    assert rows and rows[0][0] == "dedup_miss"
    assert not dispatch.pending_confirm().get("refinements"), "a separate errand must not be folded into the parked one"


def test_the_confirmed_relaunch_is_never_compared_against_itself(fresh_db, monkeypatch):
    """`resolve_confirm` pops the entry and re-escalates with `confirmed`; a stale copy left parked must not
    swallow the relaunch — the yes has to become a worker."""
    rows, _ = _drive(monkeypatch, parked=("3", HIS_WORDS), request=HIS_WORDS, context={"confirmed": True})
    assert rows and rows[0][0] == "dedup_miss"
