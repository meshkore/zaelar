"""V2-728 — THE USE CASE, end to end: «búscame piso en Gràcia» … «enséñame lo del piso que te dije».

This is the operator's own sentence turned into one causal chain, and it is the test that decides whether
V2-728 is done. Every other file here proves a PIECE — the store stores, the seam translates, the recall
narrows, the tab renders. All of them were green while the chain was still broken, because the chain is
where the pieces have to agree about the same task, and nothing was asserting that.

  1. He hands over a commission. A durable row appears WHILE the worker runs, with its start time — the
     counter goes up and he can stop thinking about it, which is the whole point («ya me olvido de esa
     tarea»).
  2. The worker delivers: five kept, and the ones it rejected WITH THEIR REASONS.
  3. It closes. The report is snapshotted onto the TASK, and a memory pill is written so plain recall — the
     kind that runs on every turn without being asked — can reach it.
  4. EIGHT MORE SEARCHES HAPPEN. The sheet cap prunes his report off disk. This is not a hypothetical: it
     is the defect the operator reported, and before V2-728 the report was simply gone at this line.
  5. Weeks later: «enséñame lo del piso que te dije». No model narrows it (INI-027 §7), and what comes back
     is the report — kept, rejected and criteria — rebuilt from the task.

WHY HERE and not in `tests/use_cases/`. That suite drives a LIVE engine with real models over LiveKit, so it
answers a different question (does the agent UNDERSTAND the sentence) and cannot run deterministically. The
case is registered there too (`tests/use_cases/cases_data.py::flat-hunt-recall-the-report`) for when the
operator runs the battery. What is asserted here is the MACHINERY behind the sentence, which is what breaks
silently and what no live run would localise.
"""
from __future__ import annotations

import asyncio

import pytest

import bus
from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo import dispatch, tasks
from nucleo.flash import task_recall as tr
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec
from tests.waiting import until
from widgets import store
from widgets.results import data as sheetdata
from widgets.results import sheet_names

KEPT = [{"title": f"Piso en Gràcia · Verdi {n}", "url": f"https://example.com/g{n}",
         "price": f"{1000 + n * 20} €/mes"} for n in range(1, 6)]
REJECTED = [{"title": f"Descartado {n}", "url": f"https://example.com/x{n}",
             "why": f"1.{400 + n} €/mes, por encima del tope de 1.200", "source": "idealista"}
            for n in range(1, 51)]


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture(autouse=True)
def _no_sessions_left_behind():
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    """The narrowing step must not call a model. Jev OFF proves the chain works without one."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: False)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def own_sheets(tmp_path, monkeypatch):
    """A widget data dir of our OWN. `store.DATA_DIR` is a module constant resolved at import, so neither an
    env var nor patching `workspace.root` reaches it — both LOOK like isolation and leave the test writing
    into the operator's real `widgets/_data/`. The assert is the guard for the guard."""
    d = tmp_path / "wdata"
    d.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", str(d))
    assert "widgets/_data" not in store.DATA_DIR, "this fixture is not isolating anything"
    return d


class _Worker(WorkerBackend):
    """A worker that fills the sheet the way a real one does — as it goes — and then delivers."""
    name = "fake"

    def __init__(self, gate: asyncio.Event):
        self._gate, self._alive = gate, False
        self.seen_spec: WorkerSpec | None = None

    async def start(self, prompt: str, *, spec: WorkerSpec) -> None:
        self.seen_spec, self._alive = spec, True

    async def send(self, text: str) -> None:
        pass

    async def events(self):
        spec = self.seen_spec
        tid = spec.task_id if spec else ""
        yield WorkerEvent(task_id=tid, type="spawned", backend=self.name)
        await self._gate.wait()
        # WHICH sheet a real worker writes to. It does not carry one in its spec: it resolves it from its own
        # task id through the single definition every side uses (`nucleo/sheets.sheet_id_for`, the V2-259
        # rule — «one errand is one sheet» named identically by whoever names it). Guessing it here instead
        # would be the test writing to a box the product never reads.
        from nucleo.sheets import sheet_id_for
        sheet = sheet_id_for(tid)
        # What a real worker does through `python -m nucleo.widget_cli data results …`.
        sheetdata.apply_action("criteria", {"sheet": sheet, "criteria": {
            "goal": "piso de alquiler en Gràcia", "hard": ["hasta 1.200 €/mes", "en Gràcia"]}})
        sheetdata.apply_action("rejected", {"sheet": sheet, "rejected": REJECTED})
        sheetdata.apply_action("present", {"sheet": sheet, "title": "Pisos en Gràcia", "items": KEPT})
        yield WorkerEvent(task_id=tid, type="result", backend=self.name,
                          data={"summary": "5 pisos en Gràcia por debajo de 1.200 €", "ok": True})
        self._alive = False
        yield WorkerEvent(task_id=tid, type="done", backend=self.name)

    async def stop(self, *, grace: float = 3.0) -> None:
        self._alive = False
        self._gate.set()

    @property
    def alive(self) -> bool:
        return self._alive

    def native_session_id(self) -> str:
        return ""


async def _hand_over_the_errand(monkeypatch, phrase: str) -> tuple[list, list]:
    """Drive the REAL dispatcher through one commission. Returns (rows while live, rows once done)."""
    from nucleo.flash import escalate
    gate = asyncio.Event()
    holder: dict = {}
    monkeypatch.setattr(dispatch, "get_backend", lambda spec: holder.setdefault("b", _Worker(gate)))
    bus.reset()
    escalate.reset()
    stop = asyncio.Event()
    listener = asyncio.create_task(dispatch.run_listener(stop))
    await asyncio.sleep(0.05)
    # `surface="lista"` is what a «búscame…» turn declares, and it is what makes the dispatcher SEAL a sheet
    # for this errand (`nucleo/sheets._sheet_open`). Without it the errand has no sheet, so there is no
    # report to snapshot and the chain below would be testing a commission that never produced anything —
    # green, and about nothing.
    escalate.escalate_to_slowbrain(phrase, context={"surface": "lista"})
    live = await until(lambda: ts.tasks_where(states=ts.LIVE_STATES, visible_only=False) or None,
                       "the dispatcher to write the durable row")
    gate.set()
    done = await until(lambda: ts.tasks_where(states=ts.DONE_STATES, visible_only=False) or None,
                       "the commission to be recorded as finished")
    stop.set()
    await asyncio.sleep(0.05)
    listener.cancel()
    return live, done


def test_the_whole_errand_from_the_phrase_to_the_report_he_asks_for_weeks_later(
        fresh_db, own_sheets, monkeypatch):
    written: list[str] = []
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda text, **kw: written.append(text))

    # ── 1 · he hands it over, and can stop thinking about it ────────────────────────────────────────────
    live, done = asyncio.run(_hand_over_the_errand(monkeypatch, "búscame piso de alquiler en Gràcia"))
    assert len(live) == 1, "no durable row while the worker was running: the counter he watches is a lie"
    assert live[0]["started_at"], "«En curso» shows the START TIME — he asked for it by name"
    assert live[0]["visible"] is True

    # ── 2-3 · it closes, and the report becomes the TASK's ──────────────────────────────────────────────
    assert len(done) == 1
    task_id = done[0]["id"]
    assert done[0]["state"] == "done" and done[0]["outcome"]
    parts = tasks.artifacts(task_id)
    assert len(parts["result"]["items"]) == 5, "the five he keeps"
    assert len(parts["considered"]["rows"]) == 50, (
        "«y otros 50 que ha descartado, pues todo eso tiene que quedar vinculado» — the rejected rows are "
        "the half that only ever survived as a COUNT")
    assert parts["considered"]["rows"][0]["why"], "a rejection with no reason cannot be discussed"
    assert parts["criteria"]["hard"], "what it searched WITH travels with what it found"

    # …and plain recall can reach it, without anyone naming the word «tarea».
    assert any(t.startswith(f"[task:{task_id}]") for t in written), (
        f"nothing about this commission reached memory, so «¿encontraste algo de pisos?» —a question that "
        f"never says «tarea»— still retrieves the conversation and not the errand. Written: {written}")

    # ── 4 · ENOUGH more searches to pass the cap. It prunes his report off disk. ────────────────────────
    # Driven off the CONSTANT, not a number copied out of it: the cap moved from 8 to 40 with V2-728 (it
    # stopped being a data-loss cap once the task owned the report), and a hard-coded 9 here would have
    # turned this step into a no-op silently — the chain would still pass, over a sheet that was never
    # actually pruned, which is the one thing this step exists to force.
    for n in range(sheet_names._MAX_SHEETS + 1):
        sheetdata.apply_action("present", {"sheet": f"otra{n}", "title": f"Otra búsqueda {n}",
                                           "items": [{"title": "x"}]})
        sheet_names.prune_sheets()
    assert not store.exists(sheet_names.sheet_key(task_id)), (
        "the sheet cap did not prune — this test is no longer reproducing the defect it exists for")

    # ── 5 · «enséñame lo del piso que te dije» ──────────────────────────────────────────────────────────
    verdict = tr.voice_turn("enséñame lo del piso que te dije")
    assert verdict["ask"] is None, f"it asked instead of answering: {verdict}"
    assert verdict["show"] == f"results::{task_id}"
    assert verdict["rebuilt"] is True, "the sheet was pruned, so it HAD to be rebuilt from the task"

    back = sheetdata.view_data(task_id)
    assert [i["title"] for i in back["items"]] == [i["title"] for i in KEPT]
    assert len(back["rejected"]) == 50, "the discarded pile came back with the report, not just the kept five"
    assert back["criteria"]["hard"]


def test_and_the_finished_row_offers_the_button_that_does_it_without_talking(fresh_db, own_sheets, monkeypatch):
    """The other half of what he asked for: «se va a esa lista, le da el botón y ve los datos derivados».

    A voice tool is not reachable from a click. The row has to SAY it has a report (`has_results`, which is
    what decides whether the button is drawn — a button that opens nothing is worse than no button)."""
    asyncio.run(_hand_over_the_errand(monkeypatch, "búscame piso de alquiler en Gràcia"))
    rows = tasks.board("done")
    assert len(rows) == 1
    assert rows[0]["has_results"] is True, "the finished row does not know it has a report, so no button"

    # …and a commission that kept nothing must NOT offer one.
    ts.task_put({"id": "empty", "title": "qué tiempo hace", "goal": "qué tiempo hace", "state": "done",
                 "mode": "now", "visible": True, "created_at": 10, "finished_at": 20})
    assert [r["has_results"] for r in tasks.board("done") if r["id"] == "empty"] == [False]
