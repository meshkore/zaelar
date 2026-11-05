"""The operator's long search, replayed through the end-state doors with no model (V2-852, companion of battery C13).

The fixture (`fixtures/v852_long_search_flow.json`) is his request, the end state the engine inferred for it, and the
ordered worker acts of the original flow and of its relaunch, recorded from his engine and stripped of ids and hosts.
The replay feeds them through the real doors — `circuit.spec.born` (with the recorded inference standing in for the
model), the pulse's `circuit.tick`, `circuit.close` and the ledger's `closed` → `circuit.settle` — over a results card
whose only change is the one the recorded acts made (empty until the first appended row), and asserts:

  (6) a card-presence predicate never becomes the row's end state (`probe.presence_only`);
  (7) nothing attests «met» or ends the row while the worker still acts; the row ends once, by `settle`, `done`,
      after the worker's last act.

(8) is not replayed here: the repetitions he heard come from the CALLERS of the out-of-turn door (the pulse
re-asking, the voice queue re-queuing an unconfirmed playout), and the door itself already refuses a second delivery
of one key, so feeding it the recorded calls would be green by construction. Battery C13 measures (8) live.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import ledger as T
from nucleo.circuit import spec
from tests.agent_headless.e2e.task_battery.probe import presence_only

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "v852_long_search_flow.json").read_text(encoding="utf-8"))
UID = "replay-1"
STEP_S = circuit.CHECK_EVERY_S
#: The declared debt: both invariants are red on the V2-851 stack (92edbc9f8) — the recorded inference opens a
#: card-presence spec on the row and the pulse attests it «met» at the first appended row. Strict: the fix that
#: restores I2 (V2-852 T10) turns them XPASS, and its writer removes this marker in the same commit.
BASELINE_RED = pytest.mark.xfail(reason="V2-852 T10 / invariant I2: the end state is the request's, met only at the "
                                        "row's end", strict=True)


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db(); spec.reset()
    yield
    spec.reset(); memdb.reset_db()


@pytest.fixture
def replay(monkeypatch):
    """The product around the doors: a results card the recorded acts fill, the recorded inference, a record of what
    the doors emitted. Returns `run(name)` → (events emitted with the replay clock, the time of the last act)."""
    from nucleo import truth
    from voice import observer
    card = {"empty": True}
    emitted: list[dict] = []
    clock = [0.0]

    def view(wid):
        return dict(card) if truth._base(wid) == "results" else None

    async def inferred(goal, **_):
        return json.loads(json.dumps(FIXTURE["inferred_done_when"]))

    async def told(*_a, **_k):
        return None

    def emit(kind, label, text="", role="", extra=None, **_):
        emitted.append({"t": clock[0], "kind": kind, "label": label, **dict(extra or {})})
    monkeypatch.setattr(truth, "widget_view", view)
    monkeypatch.setattr(spec, "infer", inferred)
    monkeypatch.setattr(spec, "_tell_worker", told)
    monkeypatch.setattr(observer, "emit", emit)

    def run(name: str):
        from nucleo.workers.session_record import SessionRecord
        events = next(r for r in FIXTURE["runs"] if r["name"] == name)["events"]
        acts = [e for e in events if e["event"] == "worker_act"]
        last = max(e["t"] for e in acts)
        ts.task_put({"id": UID, "goal": FIXTURE["request"], "kind": "generic", "state": "running"})
        rec = SessionRecord(task_id="1", goal=FIXTURE["request"])
        rec.uid, rec.status = UID, "running"
        t0 = time.time()

        async def go():
            spec.born(rec, {"src": "voice"})
            for _ in range(5):
                await asyncio.sleep(0)
            t, i = 0.0, 0
            while t <= last:
                while i < len(acts) and acts[i]["t"] <= t:
                    if acts[i]["door"] in FIXTURE["fills_the_card"]:
                        card["empty"] = False
                    i += 1
                clock[0] = t
                circuit.tick(now=t0 + t)
                t += STEP_S
            clock[0] = last + STEP_S          # the worker's own ending, after its last act
            rec.status, rec.ok, rec.result_summary = "done", True, "the documented best pick"
            circuit.close(rec, relay_cap=0)
            T.closed(rec)
        asyncio.run(go())
        return emitted, last
    return run


@BASELINE_RED
def test_a_card_presence_predicate_never_becomes_the_rows_end_state(replay):
    replay("T19")
    got = spec.of_task(UID) or {}
    assert not presence_only(got.get("done_when")), (
        f"the row's end state is a card-presence predicate {got.get('done_when')} (source {got.get('source')}): "
        "a search for a documented best pick among a wide base was attested on its first row")


@BASELINE_RED
def test_nothing_ends_or_is_met_while_the_worker_still_acts(replay):
    """The relaunch (T19) is the run that worked long: the original (T8) was stopped 2 minutes after its only append."""
    emitted, last = replay("T19")
    early = [e for e in emitted if e["t"] <= last and (
        (e["kind"] == "verdict" and e.get("verdict") == "met") or e["kind"] == "task_state")]
    assert not early, f"attested or ended before the worker's last act at {last} s: {early[:3]}"
    met = [e for e in emitted if e["kind"] == "verdict" and e.get("verdict") == "met"]
    assert len(met) <= 1, f"«met» attested {len(met)} times for one row"
    endings = [e for e in emitted if e["kind"] == "task_state" and e.get("task_id") == UID]
    assert [(e.get("state"), e.get("writer")) for e in endings] == [("done", "settle")], endings
    assert ts.task_get(UID)["state"] == "done"


@pytest.mark.parametrize("dw, only", [
    ({"widget": "results", "field": "empty", "is": False}, True),
    ({"all": [{"widget": "results", "field": "empty", "is": "false"}]}, True),
    ({"canvas": "results", "expect": "visible"}, True),
    ({"widget": "results", "collection": "items"}, True),
    ({"all": [{"widget": "results", "field": "empty", "is": False}, {"canvas": "results", "expect": "visible"}]}, True),
    ({"widget": "results", "collection": "items", "count": {"min": 300}}, False),
    ({"widget": "results", "collection": "items", "where": {"price<=": 30000}}, False),
    ({"widget": "results", "field": "layout", "is": "compare"}, False),
    ({"widget": "documento", "field": "focus", "has": "sources"}, False),
    ({"widget": "agenda", "collection": "meetings", "expect": "added"}, False),
    ({}, False),
    (None, False),
])
def test_a_presence_predicate_is_read_from_the_grammar(dw, only):
    assert presence_only(dw) is only
