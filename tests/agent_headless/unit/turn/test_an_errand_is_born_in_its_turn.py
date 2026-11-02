"""An errand is born IN its turn, with his whole request (V2-844 F1a, 2026-11-02).

A car request dictated in fragments: the turn that finally launched it had «Okay.» as its own words, its cut sentence
joined in front of it only for the verdict. The listing door handed the worker `operator_text or query` — the
fragment — and the errand that survived was called «Okay.». Its durable row only appeared when the dispatcher picked
the escalation up, so until then the turn's sheet and launches belonged to nobody, under a counter id of their own.

Now an errand is born where the turn decides it: a durable row (`starting`, off the board) with its uid, which also
names its sheet, and with the WHOLE request the turn's verdict judged. The dispatcher adopts that row; a delivery at
the first rung closes it; a launch folded into another errand or refused leaves nothing behind.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, tasks_store as ts
from nucleo.acts import errand, search_sheet
from nucleo.circuit import ledger
from nucleo.turn import brief_turn, turn_marks
from voice import trace

CAR_EN = ("let's focus on the car. I wanna... One of those big runners, a Toyota 4Runner. Two or three good offers. "
          "Thirty, forty, fifty thousand. Okay.", "Okay.")
CAR_ES = ("vale, el coche. Uno de esos todoterreno grandes, un Toyota 4Runner. Dos o tres buenas ofertas. Entre treinta "
          "y cincuenta mil. Vale.", "Vale.")
FLAT_EN = ("find me a flat to rent in Madrid, two bedrooms, near Retiro, under fifteen hundred. Right.", "Right.")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    errand.reset()
    turn_marks.reset()
    from nucleo.workers import ended as _ended
    _ended._LISTING_DELIVERIES.clear()
    yield
    errand.rows_settled()
    _ended._LISTING_DELIVERIES.clear()      # a delivery is shared state: it must not outlive the test that made it
    turn_marks.reset()
    trace.adopt("")
    memdb.reset_db()
    errand.reset()


def _turn(tid: str, whole: str, tail: str = "") -> None:
    """A turn admitted with a cut sentence in front of its tail (`tail`), or — no tail — a turn nothing was cut from."""
    trace.adopt(tid)
    brief_turn.remember_for_the_turn({"judged": whole})
    if tail:
        turn_marks.cut(tid, whole, tail)


def _rows() -> list[dict]:
    errand.rows_settled()
    return ts.tasks_where(states=(*ts.LIVE_STATES, *ts.DONE_STATES, ledger.STARTING), visible_only=False, limit=50)


# ── the request is the whole one ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("whole, tail", [CAR_EN, CAR_ES, FLAT_EN], ids=["car-en", "car-es", "flat-en"])
def test_a_fragment_stands_for_its_turns_whole_request(db, whole, tail):
    _turn("T39", whole, tail)
    assert errand.whole_request(tail) == whole
    assert errand.whole_request(whole) == whole


def test_a_request_with_words_of_its_own_is_kept(db):
    _turn("T39", CAR_EN[0])
    other = "and book a table for two in Seville tonight"
    assert errand.whole_request(other) == other, "a request that is not a fragment of the turn was rewritten"
    _turn("T50", "busca una guitarra acústica en Barcelona")
    assert errand.whole_request("busca una guitarra acústica en Barcelona") == "busca una guitarra acústica en Barcelona"


# ── the listing door: born before the pass, the whole request, the uid is the sheet ───────────────────────────

@pytest.fixture
def pass_rig(db, monkeypatch):
    sent: list = []
    monkeypatch.setattr(search_sheet, "_write_sheet", lambda *a, **k: None)
    monkeypatch.setattr(search_sheet, "_observe", lambda *a, **k: None)
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: sent.append(payload))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    found = {"items": [], "needs_browser": True}
    monkeypatch.setattr("search.listing.search", lambda q: {"sources": [], **found})
    return sent, found


@pytest.mark.parametrize("whole, tail", [CAR_EN, CAR_ES, FLAT_EN], ids=["car-en", "car-es", "flat-en"])
def test_a_hunt_that_hands_on_is_one_errand_with_the_whole_request(pass_rig, whole, tail):
    sent, _found = pass_rig
    _turn("T39", whole, tail)
    out = search_sheet.fast_pass("Toyota 4Runner", operator_text=tail)
    rows = _rows()
    assert len(rows) == 1, f"the hunt left {len(rows)} rows"
    row = rows[0]
    assert row["id"] == out["sheet"], "the hunt's sheet is not named by its errand's uid"
    assert row["goal"] == whole, f"the errand is called «{row['goal']}»"
    assert [p["request"] for p in sent] == [whole], "the worker was handed the fragment"
    assert sent[0]["context"]["born_uid"] == row["id"] and sent[0]["id"] == out["escalated"]
    assert "routed" not in sent[0]["context"], "the hunt's own hand-on was routed again at the portal"


def test_a_hunt_delivered_in_the_turn_ends_at_its_first_rung(pass_rig):
    sent, found = pass_rig
    found.update(items=[{"title": "4Runner 2021", "price": 41000}] * 6, needs_browser=False)
    _turn("T40", FLAT_EN[0], FLAT_EN[1])
    search_sheet.fast_pass("flat Madrid", operator_text=FLAT_EN[1])
    row = _rows()[0]
    assert row["state"] == "done" and not row["visible"] and not sent


def test_a_hunt_whose_hand_on_is_refused_leaves_no_row(pass_rig, monkeypatch):
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda *a, **k: 0)     # parked on his yes, or refused
    _turn("T41", CAR_EN[0])
    search_sheet.fast_pass("Toyota 4Runner", operator_text=CAR_EN[1])
    assert not _rows()


def test_the_listing_door_births_the_errand_before_the_pass_runs(pass_rig, monkeypatch):
    from nucleo.acts import search_listing
    seen: list = []

    def fake_pass(query, **kw):
        seen.append((kw, [dict(r) for r in _rows()]))     # settled: written by the one writer before anything else
        return {"delivered": False, "n": 0, "sheet": kw["new_sheet"], "escalated": 0, "reason": "", "ctx": ""}
    monkeypatch.setattr(search_listing, "fast_pass", fake_pass)
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr("nucleo.turn.flow_of.candidates", lambda: [])
    _turn("T42", CAR_ES[0], CAR_ES[1])
    asyncio.run(search_listing.listings({"text": CAR_ES[1]}, {"query": "Toyota 4Runner"}))
    kw, rows = seen[0]
    assert [r["state"] for r in rows] == [ledger.STARTING], "the errand did not exist when its pass started"
    assert kw["new_sheet"] == rows[0]["id"] and kw["errand_id"] and kw["operator_text"] == CAR_ES[0]


# ── the portal: every escalation is born; a relay continues its own row ─────────────────────────────────────

def test_a_turns_escalation_is_born_with_the_whole_request(pass_rig):
    sent, _ = pass_rig
    _turn("T43", CAR_EN[0], CAR_EN[1])
    tid = errand.escalate_to_slowbrain(CAR_EN[1], context={"kind": "web"})
    row = _rows()[0]
    assert row["id"] == ledger.task_uid(tid) and row["goal"] == CAR_EN[0] and row["state"] == ledger.STARTING
    assert sent[0]["context"]["born_uid"] == row["id"]


def test_a_relay_continues_its_row_and_is_not_born_again(pass_rig):
    sent, _ = pass_rig
    errand.escalate_to_slowbrain("find me a flat in Madrid", context={"kind": "web", "task_uid": "b0-1"})
    assert not _rows() and "born_uid" not in sent[0]["context"]


# ── the dispatcher adopts the row; a fold or a halt leaves nothing behind; nobody adopting it, the pulse does ──

def _listen(monkeypatch, request, ctx, *, live=None):
    import bus
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")
    monkeypatch.setattr(dispatch, "_run_session", lambda task: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_name_errand", lambda rec: None)

    async def _inject(which, msg):
        return [which]
    monkeypatch.setattr(dispatch, "inject", _inject)

    async def run():
        bus.reset()
        dispatch._SESSIONS.clear()
        if live:
            dispatch._SESSIONS[live[0]] = SessionRecord(task_id=live[0], kind="web", status="running", goal=live[1])
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        errand.escalate_to_slowbrain(request, context=ctx)
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); task.cancel()
    asyncio.run(run())
    recs = dict(dispatch._SESSIONS)
    dispatch._SESSIONS.clear()
    return recs


def test_the_dispatcher_adopts_the_row_the_turn_wrote(db, monkeypatch):
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    real_born = ledger.born

    def born_at_the_turn(tid, req, ctx=None):          # the row as the turn left it, before any worker
        uid = real_born(tid, req, ctx)
        ts.task_patch(uid, created_at=123)
        return uid
    monkeypatch.setattr(ledger, "born", born_at_the_turn)
    _turn("T44", FLAT_EN[0], FLAT_EN[1])
    recs = _listen(monkeypatch, FLAT_EN[1], {"kind": "web"})
    rows = _rows()
    assert len(rows) == 1, "the dispatcher opened a second row beside the one the turn wrote"
    rec = next(iter(recs.values()))
    assert rows[0]["id"] == rec.uid and rows[0]["goal"] == FLAT_EN[0] and rows[0]["visible"]
    assert rows[0]["state"] != ledger.STARTING
    assert rows[0]["created_at"] == 123, "the dispatcher wrote a row of its own over the one the turn was born with"
    from nucleo.circuit import continuation
    assert not continuation.continues(rec, {"born_uid": rec.uid}), "a first launch was read as a continuation"


def test_a_launch_folded_into_a_live_errand_leaves_no_row(db, monkeypatch):
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    _turn("T45", "find me a flat to rent in Madrid, two bedrooms")
    _listen(monkeypatch, "find me a flat to rent in Madrid, two bedrooms near Retiro", {"kind": "web"},
            live=("live-1", "find me a flat to rent in Madrid, two bedrooms"))
    assert not _rows(), "the folded launch's row stayed behind as an errand of its own"


def test_a_row_nobody_adopted_is_forgotten_and_an_adopted_one_is_not(db):
    old = ledger.born(90, "find me a flat in Madrid", {})
    ts.task_patch(old, started_at=1, created_at=1)
    keep = ledger.born(91, "a used acoustic guitar", {})
    ts.task_patch(keep, state="running", visible=True, started_at=1, created_at=1)
    ledger.reconciled({keep})
    ids = {r["id"] for r in _rows()}
    assert old not in ids and keep in ids


def test_a_late_birth_never_rewinds_a_row_the_dispatcher_moved_on(db):
    uid = ledger.task_uid(92)
    ts.task_put({"id": uid, "goal": "find me a flat in Madrid", "state": "running", "visible": True, "mode": "now"})
    ledger.born(92, "find me a flat in Madrid", {})
    row = next(r for r in _rows() if r["id"] == uid)
    assert row["state"] == "running" and row["visible"]
