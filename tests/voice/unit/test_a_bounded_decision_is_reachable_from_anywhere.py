"""Node 3.70 — one bounded-decision door, reachable from the turn, from memory AND from a worker.

V2-726 A1, and the operator's own objective: «a cheap decision capability available throughout
Colmena whenever a process can choose among available options». It was available in Python and
unreachable from the place with the most choosing to do — `nucleo/workers/`, `nucleo/errands/` and
`research.py` mention Jev nowhere, because a Brain Worker is a subprocess and talks to the engine
only through `/api/worker/act`.

So the fix is ONE new allowed action on that endpoint, not a second client, not a new bridge, not a
model call from inside a worker. The authentication, the piggyback and the policy are already there
and already audited.

The other half is the contract. `select_many` answered `[]` for «nothing fits», «no key», «network
down», «switched off» and «nothing to choose between» — two answers and three absences, which call
for opposite behaviour, and `task_recall` was treating a shortlist nobody had looked at as one the
chooser had narrowed. `decide` names every outcome.

⚠️ Everything here fakes the transport. `decide` is a real paid round trip, and a probe of this very
audit put four live events into the operator's timeline on 2026-09-20 (and one more while A1 was
being written, removed by hand). A test never touches the operator's real state — §7.3 rule 2.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo import jev


@pytest.fixture
def wire(monkeypatch):
    """Jev ON with the socket replaced, and the timeline captured rather than written."""
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    jev.reset_breaker()

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.answer: tuple[str, float] | None = None

        def __call__(self, state, questions, timeout_s):
            self.calls.append({"state": state, "questions": questions, "timeout_s": timeout_s})
            key = next(iter(questions))
            crit = questions[key]["criteria"]
            choice, conf = self.answer or (next(iter(crit)), 0.95)
            return {"answers": {key: {"choice": choice, "confidence": conf,
                                      "probabilities": {choice: conf}}}}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


CANDS = {"r1": "piso en Malasaña, 1200 €", "r2": "piso en Chamberí, 900 €",
         "r3": "plaza de garaje, 90 €"}


# ── the statuses: an answer is not an absence ────────────────────────────────────────────────────
def test_a_confident_pick_is_SELECTED_and_says_which(wire):
    wire.answer = ("r2", 0.91)
    d = jev.decide("which flat meets the criteria?", "under 1000 €", CANDS)
    assert d["status"] == jev.SELECTED and d["chosen"] == ["r2"] and d.ok
    assert d["confidence"]["r2"] == 0.91
    assert d["call_id"], "a decision with no id cannot be joined to the outcome it caused"


def test_none_of_them_is_ABSTAINED_not_no_match(wire):
    """«I looked and none of these fits» is an ANSWER. Forcing a pick from a closed list is how a
    chooser becomes confidently wrong — the `none` option is what makes the question honest."""
    wire.answer = ("none", 0.88)
    d = jev.decide("which flat?", "under 200 €", CANDS)
    assert d["status"] == jev.ABSTAINED and d["chosen"] == []


def test_an_unsure_pick_ABSTAINS_and_keeps_the_number(wire):
    """Below the gate the verdict is a shrug. It is still reported, with its confidence, because a
    consumer needs to log the doubt — and because A6b calibrates on exactly these."""
    wire.answer = ("r1", 0.2)
    d = jev.decide("which flat?", "under 1000 €", CANDS)
    assert d["status"] == jev.ABSTAINED and d["confidence"] == {"r1": 0.2}


def test_the_network_being_down_is_UNAVAILABLE_not_no_match(wire, monkeypatch):
    def _boom(*a, **k):
        raise OSError("network is down")
    monkeypatch.setattr(jev, "_post_many", _boom)
    jev.reset_breaker()
    d = jev.decide("which flat?", "x", CANDS)
    assert d["status"] == jev.UNAVAILABLE and d["chosen"] == []


def test_switched_off_is_DISABLED_and_reaches_nothing(wire, monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV", "0")
    d = jev.decide("which flat?", "x", CANDS)
    assert d["status"] == jev.DISABLED
    assert wire.calls == [], "the kill switch let a call through"


def test_nothing_to_choose_between_is_EMPTY_and_costs_nothing(wire):
    assert jev.decide("which flat?", "x", {})["status"] == jev.EMPTY
    assert jev.decide("", "x", CANDS)["status"] == jev.EMPTY
    assert wire.calls == []


def test_too_many_candidates_is_TOO_BIG_and_never_reaches_the_wire(wire):
    """A caller that enumerates a database would turn one cheap classifier into a slow expensive
    one, and the failure would look like a truncated verdict rather than an error."""
    huge = {str(i): f"row {i}" for i in range(jev.MAX_QUESTIONS + 1)}
    assert jev.decide("which row?", "x", huge)["status"] == jev.TOO_BIG
    assert jev.decide("which row?", "y" * (jev.MAX_STATE_CHARS + 10), CANDS)["status"] == jev.TOO_BIG
    assert wire.calls == [], "nothing oversized may reach the wire"


def test_every_status_is_a_declared_one(wire, monkeypatch):
    """No caller can branch on a status nobody documented."""
    seen = {jev.decide("p", "e", CANDS)["status"], jev.decide("p", "e", {})["status"]}
    monkeypatch.setenv("ZAELAR_JEV", "0")
    seen.add(jev.decide("p", "e", CANDS)["status"])
    assert seen <= set(jev.DECISION_STATUSES), seen


def test_an_invented_answer_can_never_come_back(wire):
    """Rule 2 of the initiative: the verdict is constrained to the ids the DOMAIN enumerated.

    ⚠️ The enforcement is TWO layers deep, and the disarm is what proved it: `_parse` already blanks
    a choice that is not a criteria key, so `decide`'s own membership check never sees one. Both are
    kept — `decide` is the door other processes reach through and must not depend on a private
    helper staying strict — but the test asserts against the layer that actually holds, because a
    test aimed at the layer that does NOT is a test that cannot fail. Same class as the dead route
    this initiative started from.
    """
    wire.answer = ("r9-invented", 0.99)
    d = jev.decide("which flat?", "x", CANDS)
    assert d["status"] == jev.NO_MATCH and d["chosen"] == []

    parsed = jev._parse({"answers": {"decision": {"choice": "r9-invented", "confidence": 0.99}}},
                        answer_key="decision", allowed=CANDS)
    assert parsed[0] == "", "an id nobody enumerated survived the parse"


# ── bounds: the voice turn is never made to queue ────────────────────────────────────────────────
def test_background_callers_share_a_limited_number_of_slots(wire):
    """A worker sweeping a hundred rows must not be able to starve anything else. The voice brief
    does not take these slots at all — it is one call per turn on a deadline, and making it wait
    behind a background sweep is the one way this module could make a turn SLOWER."""
    assert jev._BG_LIMIT >= 1
    for _ in range(jev._BG_LIMIT):
        assert jev._bg_sem.acquire(timeout=0.1)
    d = jev.decide("which flat?", "x", CANDS, deadline_s=0.2)
    assert d["status"] == jev.EXPIRED, "a background caller jumped the queue"
    for _ in range(jev._BG_LIMIT):
        jev._bg_sem.release()
    assert jev.decide("which flat?", "x", CANDS)["status"] in (jev.SELECTED, jev.ABSTAINED)


def test_the_turn_brief_does_not_go_through_the_background_gate(wire):
    """The brief keeps its own door (`ask_many`), fired at turn start and read by peek. Proof that
    A1 did not quietly put the hot path behind a semaphore: with every slot taken, it still flies."""
    from nucleo.flash import turn_brief as tb
    for _ in range(jev._BG_LIMIT):
        assert jev._bg_sem.acquire(timeout=0.1)
    try:
        h = tb.ask("dale al play", open_ids=[])
        if h and h.get("event"):
            h["event"].wait(2.0)
        assert jev.peek(h), "the voice brief was made to queue behind background decisions"
    finally:
        for _ in range(jev._BG_LIMIT):
            jev._bg_sem.release()


# ── the worker door ──────────────────────────────────────────────────────────────────────────────
def test_the_policy_allows_a_bounded_decision(wire):
    from nucleo import worker_policy as wp
    assert wp.classify_act("decide", {}) == wp.ALLOW


def test_a_real_worker_reaches_the_SAME_primitive_through_its_token(wire):
    """The point of A1, end to end: an authenticated worker request lands on `jev.decide`.

    It goes through `_exec_allow`, which is the function `/api/worker/act` calls after verifying the
    task token — so this exercises the actual door, not a mirror of it.
    """
    from nucleo import worker_api as wapi

    class _Rec:
        task_id = "task-7"
        goal = "find a flat"

    wire.answer = ("r2", 0.93)
    res = asyncio.run(wapi._exec_allow(
        "decide", {"purpose": "which flat meets the criteria?", "evidence": "under 1000 €",
                   "candidates": CANDS}, _Rec()))
    assert res["ok"] is True
    assert res["result"]["status"] == jev.SELECTED and res["result"]["chosen"] == ["r2"]
    assert len(wire.calls) == 1, "the worker door did not reach the transport"
    assert "worker:task-7" in wire.calls[0]["questions"]["decision"]["instructions"], (
        "the decision does not record WHO asked, so it cannot be attributed in the timeline")


def test_a_worker_may_pass_a_plain_list_of_candidates(wire):
    """Workers build candidates from parsed rows, and a list is the natural shape. Accepting it here
    is what stops each worker from inventing its own id scheme."""
    from nucleo import worker_api as wapi

    class _Rec:
        task_id = "task-8"

    wire.answer = ("2", 0.9)
    res = asyncio.run(wapi._exec_allow(
        "decide", {"purpose": "which one?", "candidates": ["first row", "second row"]}, _Rec()))
    assert res["result"]["chosen"] == ["2"]


def test_the_worker_result_carries_the_DECISION_and_nothing_else(wire):
    """Credentials and other tasks' data can never reach a worker through this door — by
    construction, because `decide` returns only its own verdict. Pinned so a later 'helpful' field
    (the state? the key? the other candidates' rows?) has to argue with a test first."""
    from nucleo import worker_api as wapi

    class _Rec:
        task_id = "task-9"

    res = asyncio.run(wapi._exec_allow("decide", {"purpose": "p", "candidates": CANDS}, _Rec()))
    assert set(res["result"]) == {"status", "chosen", "confidence", "latency_ms",
                                  "call_id", "provenance"}
    assert set(res) <= {"ok", "result", "error"}


def test_a_malformed_worker_payload_is_an_ANSWER_not_a_crash(wire):
    """A worker that gets an exception back learns nothing and usually retries the same way. Every
    bridge in this engine fails soft with something the worker can branch on (V2-644's lesson, paid
    for with four minutes of a worker driving a browser because a silent [] blamed the module)."""
    from nucleo import worker_api as wapi

    class _Rec:
        task_id = "task-10"

    res = asyncio.run(wapi._exec_allow("decide", {"purpose": "p", "candidates": {}}, _Rec()))
    assert res["ok"] is True and res["result"]["status"] == jev.EMPTY


def test_the_worker_reaches_it_the_SAME_WAY_it_reaches_every_other_payload(wire, tmp_path,
                                                                             monkeypatch):
    """`@file.json`, not inline JSON — and this is not a style choice.

    The worker's own prompt says it in capitals, from a measured incident (V2-379): our permission
    gate rejects an argument containing braces and quotes, so an inline JSON never reaches the
    command at all. The first version of this subcommand took the candidates inline, which would
    have made it unusable by the only process it was built for — a capability a worker cannot invoke
    is one it narrates instead of using. Caught by reading the prompt that teaches the bridges.
    """
    from nucleo import worker_bridge as wb
    import json as _json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "elige.json").write_text(_json.dumps(
        {"purpose": "cuál cumple", "evidence": "menos de 1000 €", "candidates": CANDS}),
        encoding="utf-8")
    sent = {}
    monkeypatch.setattr(wb, "_post", lambda path, payload: sent.update(payload) or {"ok": True})
    monkeypatch.setenv("ZAELAR_TASK_ID", "task-11")
    monkeypatch.setenv("ZAELAR_TASK_TOKEN", "tok")
    assert wb.main(["decide", "@elige.json"]) == 0
    assert sent["action"] == "decide"
    assert sent["payload"]["candidates"] == CANDS


def test_the_worker_PROMPT_declares_the_door(wire):
    """A door nobody is told about is a door nobody uses. The prompt that teaches `ask`/`act`/`say`
    teaches this one too, with the shape and with what the statuses mean."""
    import pathlib as _p
    src = (_p.Path(__file__).resolve().parents[3] / "nucleo" / "dispatch_prompts.py").read_text(
        encoding="utf-8")
    assert "worker_bridge decide" in src, "the worker is never told the bounded-decision door exists"
    assert "abstained" in src, "…nor what «none of these fits» looks like when it answers"


def test_a_worker_deadline_is_bounded_by_us(wire):
    """A worker has no latency budget of its own but it does have a Bash timeout, so an unbounded
    wait would surface as a worker that died mid-errand with nothing to report."""
    from nucleo import worker_api as wapi
    assert wapi._decide_deadline({"deadline_s": 9999}) == 20.0
    assert wapi._decide_deadline({"deadline_s": 0.01}) == 0.5
    assert wapi._decide_deadline({}) is None
    assert wapi._decide_deadline({"deadline_s": "nonsense"}) is None


# ── memory/task recall is the third caller, and it already exists ────────────────────────────────
def test_task_recall_is_a_real_consumer_of_the_same_module(wire, monkeypatch):
    """«Voice, memory and a headless worker reach the same primitive» — the third one has been in
    production since V2-728, and this pins that A1 did not fork it into a parallel path."""
    from nucleo.flash import task_recall as tr
    rows = [{"id": "t1", "title": "piso", "goal": "buscar piso"},
            {"id": "t2", "title": "vuelos", "goal": "buscar vuelos"}]
    monkeypatch.setattr(tr, "candidates", lambda q, limit=5: rows)
    wire.answer = ("strong", 0.9)
    out = tr.resolve("lo del piso que te dije")
    assert len(wire.calls) == 1, "task recall stopped reaching the chooser"
    assert out["status"] in (jev.SELECTED, jev.NO_MATCH, jev.UNAVAILABLE, jev.DISABLED, jev.EMPTY)
