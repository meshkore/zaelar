"""V2-835 T4 — every relaunch of a commission keeps its END STATE, and a state already true at birth proves nothing.

search-buy-used-car ES (2026-11-02): worker:1 was born with its spec on the task row; the first provider tier ran out of quota and
the provider relay relaunched onto DeepSeek carrying the `task_uid` but not the `done_when`. `spec.born` returned
on `relay_gen` («the spec is already on the row») and the fresh record never read it, so the circuit judged the
errand `undeclared` and nothing measured whether it was done. The same hole was open on the blown-context
handoff, the stall restart and the rate-limit retry. The class: a relaunch's end state is the ROW's, read at the
one door every commission passes (`ledger.opened` → `spec.born`), never something each caller must remember.

Second half: a follow-up inherited a sheet that already held rows; its `results.empty = false` was true before the
worker read a page and the pulse settled the new commission «met and verified». An end state already true at its
commission's birth is never read as met.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import ledger as T
from nucleo.circuit import spec as _spec
from nucleo.circuit import verify as _verify
from nucleo.workers import relay
from nucleo.workers import rate_retry
from nucleo.workers.session import SessionRecord

DW = {"all": [{"widget": "agenda", "collection": "tasks", "where": {"title~": "GLC 220d"}}]}
UID = "808f23-1"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    _spec.reset()
    sent = []
    from nucleo.acts import errand as escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: sent.append((req, context)))
    state = {"met": False}
    monkeypatch.setattr(_verify, "check", lambda dw, now=None: state["met"] if dw else None)
    yield sent, state
    _spec.reset()
    memdb.reset_db()


def _first_worker(source="voice+inferred", **kw) -> SessionRecord:
    """worker:1 — its commission recorded, its end state opened and persisted on the row (event 263771)."""
    ts.task_put({"id": UID, "goal": "coches GLC 220d", "state": "running", "created_at": int(time.time())})
    rec = SessionRecord(task_id="1", goal="Buscar y comparar GLC 220d 4MATIC en toda España", kind="web", uid=UID,
                        status="error", ok=False, **kw)
    rec.done_when = dict(DW)
    assert _spec.open(DW, text=rec.goal, source=source, task_id=UID)
    return rec


def _relaunched(ctx: dict) -> SessionRecord:
    """The fresh record, built the way the dispatcher's listener builds it, recorded at the one door."""
    rec = SessionRecord(task_id="2", goal="Buscar y comparar GLC 220d 4MATIC en toda España", kind="web",
                        relay_gen=int(ctx.get("relay_gen", 0) or 0), uid=str(ctx.get("task_uid", "") or ""),
                        done_when=dict(ctx.get("done_when") or {}))
    T.opened(rec, ctx)
    return rec


def _provider_failover(rec):
    rec.provider_down = {"next": "deepseek"}
    relay.relay_out_of_fuel(rec, relay_cap=3)


def _context_handoff(rec):
    rec.context_full = {"tokens": 200_000}
    relay.relay_out_of_fuel(rec, relay_cap=3)


def _stall_restart(rec):
    rec.error_class = "stalled"
    relay.restart_stalled(rec)


def _rate_retry(rec):
    rec.result_summary = "API Error: 429 rate limit exceeded, please retry"
    assert rate_retry.relaunch_after_rate(rec, 3, schedule=lambda wait, go: go())


PATHS = [_provider_failover, _context_handoff, _stall_restart, _rate_retry]


@pytest.mark.parametrize("restarted", [False, True], ids=["same-process", "after-restart"])
@pytest.mark.parametrize("path", PATHS, ids=[p.__name__.strip("_") for p in PATHS])
def test_every_relaunch_judges_the_commission_by_its_own_end_state(world, path, restarted):
    sent, _ = world
    path(_first_worker())
    assert len(sent) == 1, "the path relaunched nothing"
    _, ctx = sent[0]
    assert ctx["task_uid"] == UID
    if restarted:
        _spec.reset()                    # the RAM ledger died with the process; the row is all that is left
    rec = _relaunched(ctx)
    assert rec.done_when == DW, "the relaunch lost what «done» means for the commission"
    assert circuit.verdict_of(rec)[0] == "unmet", "judged without its end state"
    assert [e["task_id"] for e in _spec.open_specs()] == [UID], "one owed end state for one commission"


def test_a_relaunch_keeps_the_tries_already_spent(world):
    """The row is the truth for the BOUND too: a re-opened spec started at `tries = 0` and the retry budget reset."""
    sent, _ = world
    rec = _first_worker()
    e = _spec.open_specs()[0]
    e["tries"] = 1
    _spec.persist(UID, e)
    _provider_failover(rec)
    _spec.reset()
    _relaunched(sent[0][1])
    assert _spec.open_specs()[0]["tries"] == 1


# An end state on the commission's sheet that says more than «it has something» (V2-852 T10: a presence-only spec is
# a card's state, never a row's end state — it is not born).
SHEET_DW = {"all": [{"widget": "results", "field": "counts.shown", "is": "3"}]}


def _born_with(uid: str, dw: dict, ctx: dict) -> SessionRecord:
    ts.task_put({"id": uid, "goal": "coches", "state": "running", "created_at": int(time.time())})
    rec = SessionRecord(task_id=uid[-1], goal="Buscar GLC 220d de ocasión", kind="web", uid=uid, done_when=dict(dw))
    own = T.task_uid(uid[-1])             # what `opened` names a new commission — and its own sheet
    T.opened(rec, {"src": "voice", **{k: (own if v == "own" else v) for k, v in ctx.items()}})
    return rec


def test_a_follow_up_on_an_inherited_sheet_already_full_is_never_read_as_met(world):
    """worker:3 — the continuity decision handed it worker:1's sheet, which already held rows."""
    _, state = world
    state["met"] = True
    rec = _born_with("808f23-3", SHEET_DW, {"sheet": UID})
    e = _spec.open_specs()[0]
    assert e["done_when"]["all"][0]["widget"] == f"results::{UID}"
    assert e.get("met_at_birth") and _spec.attest(e) is None
    assert circuit.tick(now=time.time() + 60) == [], "the pulse settled a commission that had done nothing"
    assert circuit.verdict_of(rec)[0] == "unverifiable"


@pytest.mark.parametrize("dw, ctx", [
    (DW, {}),                             # «add X» with X already there: the order's own card, no sheet
    (DW, {"sheet": UID}),                 # an inherited sheet the end state does not read
    (SHEET_DW, {"sheet": "own"}),         # the commission's OWN sheet (a row and its sheet share the name)
], ids=["idempotent-order", "inherited-sheet-not-read", "own-sheet"])
def test_an_order_already_true_on_its_own_card_is_still_met(world, dw, ctx):
    """Narrow on purpose: an idempotent order is met by the state it asked for, whoever was first."""
    _, state = world
    state["met"] = True
    rec = _born_with("808f23-5", dw, ctx)
    e = _spec.open_specs()[0]
    assert not e.get("met_at_birth") and _spec.attest(e) is True
    assert circuit.verdict_of(rec)[0] == "met"


def test_a_write_absorbed_into_a_row_he_held_stays_met(world):
    """T-19 R10: `existing` is the order's own outcome and outranks met-at-birth, even on an inherited sheet."""
    _, state = world
    state["met"] = True
    _born_with("808f23-3", SHEET_DW, {"sheet": UID})
    e = _spec.open_specs()[0]
    e["existing"] = {"title": "GLC 220d"}
    assert _spec.attest(e) is True
    e2 = _spec.open(SHEET_DW, task_id="808f23-6")
    e2["existing"] = {"title": "GLC 220d"}
    from nucleo.circuit import continuation as _cont
    _cont.mark_met_at_birth(e2, SessionRecord(task_id="6", goal="g", uid="808f23-6"), {"sheet": UID})
    assert not e2.get("met_at_birth") and _spec.attest(e2) is True


def test_an_end_state_that_becomes_true_later_is_still_met(world):
    _, state = world
    rec = _born_with("808f23-4", SHEET_DW, {"sheet": UID})
    state["met"] = True
    assert circuit.verdict_of(rec)[0] == "met"


def test_a_continuation_is_never_re_inferred_with_a_model(world, monkeypatch):
    """A row with no end state yet (inference pending) and a quota-parked resume (no `relay_gen`): no second guess."""
    asked = []

    async def infer(goal, **k):
        asked.append(goal)
        return DW
    monkeypatch.setattr(_spec, "infer", infer)
    monkeypatch.setattr(_spec, "_schedule", lambda coro: (asked.append("scheduled"), coro.close()))
    ts.task_put({"id": UID, "goal": "coches", "state": "running", "created_at": int(time.time())})
    for ctx in ({"src": "provider_failover", "task_uid": UID, "relay_gen": 1},
                {"src": "quota_resume", "task_uid": UID}):
        rec = _relaunched(ctx)
        assert rec.done_when == {} and _spec.open_specs() == []
    assert asked == [], "a continuation asked a model for an end state its commission already had or never got"


def test_the_harness_retry_neither_resets_nor_burns_the_budget(world):
    """`circuit.close` on an unmet ending relaunches with `tries + 1`; the relaunch reads exactly that back, and its
    own unmet ending is judged against the SAME budget (retries=2: two relaunches, then the truth)."""
    sent, _ = world
    rec = _first_worker(source="voice")     # a DECLARED end state: an inferred one never relaunches
    budget = circuit.retries()
    for spent in range(budget):
        rec.status, rec.ok, rec.handoff = "done", True, ""
        assert circuit.close(rec, relay_cap=9) == "started"
        _, ctx = sent[-1]
        assert ctx["task_uid"] == UID
        _spec.reset()                    # judged from the row, not from this process's copy
        rec = _relaunched(ctx)
        assert _spec.open_specs()[0]["tries"] == spent + 1, "the relay reset or burned the retry budget"
    rec.status, rec.ok, rec.handoff = "done", True, ""
    assert circuit.close(rec, relay_cap=9) == "unmet" and len(sent) == budget
