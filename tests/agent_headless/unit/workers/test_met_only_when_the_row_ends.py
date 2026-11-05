"""V2-852 T10 · «Met» only when the row ends, and the end state is the request's (invariant I2).

Measured in his session of 2026-11-05: an errand to find second-hand cars came with an end state on a collection no
card declares; birth rewrote it into «the results card is not empty», the pulse read it 325 times («not met yet»
each time) and attested «met» on the FIRST row that landed — while the worker kept working for eighteen more minutes.
Now: a worker row's end state is attested once, at its ending (`close` → `settle`), never by the pulse mid-run; an
unreadable clause is dropped, never rewritten into a card's state; the end state the worker states at checkpoint 1
becomes the row's; and a spec that stays unmet is said when what is missing changes, not at every read.

The variants are in other domains on purpose (a meeting in the agenda, a document), so the fix holds for any errand.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from nucleo import circuit
from nucleo.circuit import spec

THERE = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Rowan"}}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "w"))
    from widgets.agenda import data as agenda, gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    db = agenda.load_db()
    db["meetings"] = [{"id": "m1", "title": "Rowan review", "date": "2026-11-06", "startTime": "10:00", "endTime": "10:30"}]
    store.save(agenda.WIDGET_ID, db)
    emitted: list = []
    monkeypatch.setattr(spec, "_emit", lambda label, e, **extra: emitted.append((label, extra)))
    from nucleo.circuit import verdict as _verdict
    verdicts: list = []
    monkeypatch.setattr(_verdict, "emit", lambda v, **k: verdicts.append(v.name))
    yield emitted, verdicts
    spec.reset()
    memdb.reset_db()


def _worker(uid: str = "u-852", **kw):
    from nucleo.workers.session import SessionRecord
    r = SessionRecord(task_id=uid[-1], goal="book a review with Rowan and tell me when", uid=uid)
    r.ok, r.result_summary = True, "Booked."
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_an_end_state_true_mid_run_is_not_met_until_the_row_ends(world):
    _emitted, verdicts = world
    t0 = time.time()
    e = spec.open(THERE, text="book a review with Rowan", source="voice", task_id="u-852", now=t0)
    for dt in range(0, 400, 7):                    # the pulse beats for minutes while the worker still works
        assert circuit.tick(now=t0 + dt) == [], "the pulse attested a worker row's end state mid-run"
    assert e["status"] == "started" and e["checks"] == 0, "a worker row's spec is not polled by the pulse"
    assert verdicts == [], "a verdict was said before the row ended"
    rec = _worker(done_when=THERE)
    assert circuit.close(rec, relay_cap=2) == "met"          # read ONCE, at its ending
    assert e["status"] == "met" and verdicts == ["met"]


def test_an_unreadable_clause_is_dropped_never_rewritten_into_a_cards_state(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": False, "body": "x"} if wid == "documento" else {})
    got = spec.parse('{"all": [{"widget": "documento", "collection": "drafts", "where": {"title~": "Q3"}}]}')
    assert got is None, f"an undeclared collection became the card's state: {got}"
    got = spec.parse('{"all": [{"widget": "documento", "field": "content", "has": "Q3"}]}')
    assert got is None, f"an unknown field became the card's state: {got}"


def test_the_inference_is_not_offered_a_cards_emptiness(monkeypatch):
    monkeypatch.setattr(spec, "_readable", lambda: {"results": {"collections": [], "empty": True},
                                                    "agenda": {"collections": ["meetings"], "empty": False}})
    system = spec._infer_messages("find me a flat to rent in Lisbon")[0]["content"]
    assert "agenda: collections meetings" in system
    cards = system.split("only these collections and fields):", 1)[1]
    assert "agenda: collections meetings" in cards and "results" not in cards and "`empty`" not in system


def test_the_end_state_the_worker_states_becomes_the_rows(world, monkeypatch):
    from nucleo import dispatch
    rec = _worker(uid="u-853")
    born = spec.open({"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "nobody"}}]},
                     text=rec.goal, source="voice+inferred", task_id="u-853")
    born["tries"] = 1
    monkeypatch.setitem(dispatch._SESSIONS, "3", rec)
    spec.session_goal("3", THERE)
    owed = [x for x in spec.open_specs() if x.get("task_id") == "u-853"]
    assert len(owed) == 1 and owed[0]["source"] == "worker" and owed[0]["done_when"]["all"][0]["where"] == {"title~": "Rowan"}
    assert owed[0]["tries"] == 1, "restating the end state never resets the retry bound"
    assert (spec.of_task("u-853") or {}).get("source") == "worker", "the row's spec artifact is the worker's"


def test_an_unmet_spec_is_said_when_what_is_missing_changes_not_at_every_read(world):
    emitted, _ = world
    gone = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Quinn"}}]}
    e = spec.open(gone, text="x", source="flash", widget="agenda", action="add_meeting", now=1000.0)
    for _ in range(25):
        assert spec.attest(e) is False
    unmet = [x for x in emitted if x[0].startswith("❌")]
    assert len(unmet) == 1 and e["checks"] == 25, f"{len(unmet)} identical «not met yet» events for one spec"


@pytest.mark.parametrize("dw", [
    {"all": [{"widget": "documento", "field": "empty", "is": "false"}]},
    {"all": [{"canvas": "agenda", "expect": "visible"}]},
    {"widget": "agenda", "collection": "meetings"},
], ids=["not-empty", "visible", "bare-rows"])
def test_a_cards_presence_is_never_a_rows_end_state(world, monkeypatch, dw):
    """Whatever wrote it — the escalation, the inference or the worker — «the card has something» is not born."""
    from nucleo import dispatch, truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": False, "body": "x"})
    assert spec.presence_only(dw) and spec.parse(__import__("json").dumps(dw)) is None
    rec = _worker(uid="u-854")
    monkeypatch.setitem(dispatch._SESSIONS, "4", rec)
    spec.session_goal("4", dw if "all" in dw else {"all": [dw]})
    assert not rec.done_when and not spec.of_task("u-854"), "the worker's presence-only goal became the row's"
    assert not spec.presence_only({"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Rowan"}}]})
