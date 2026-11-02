"""Who owns each surface, measured in shadow (V2-844 F0, 2026-11-02).

A car request dictated in fragments opened three results sheets. Measured on the timeline: the turn's own fast pass
signed its show `sheet:<sid>`, so the arbiter logged «task-owned» for a box no errand owned; a turn DISCARDED
unanswered (T37) still wrote and showed its sheet 2.7 s later; the errand that survived was called «Okay.» — the last
fragment, not the joined request; and the flow door and the dispatcher's dedup gave opposite answers about the same
turn within 5 s. None of it was counted anywhere.

F0 changes no behaviour: it labels the turn's show by who owns the box, and records every show and write with its
would-be owner and every violation, so the next phases have a baseline per class.
"""
from __future__ import annotations

import pytest

from nucleo.acts import canvas_arbiter, surface_owner as so
from nucleo.dispatch import confirm
from voice import trace

CAR_EN = ("let's focus on the car. I wanna... One of those big runners. Kind of fourth renter. Two or three good "
          "offers. Thirty, forty, fifty. Sorry. Okay.", "Okay.")
CAR_ES = ("vale, el coche. Uno de esos todoterreno grandes, un cuatro runner. Dos o tres buenas ofertas. Entre treinta "
          "y cincuenta mil. Perdona. Vale.", "Vale.")
FLAT_EN = ("find me a flat to rent in Madrid, two bedrooms, near Retiro, under fifteen hundred. Right.", "Right.")


@pytest.fixture
def events(monkeypatch):
    for d in (so._CLAIMS, so._DISCARDED, so._LAUNCHED, so._JOINED, so._FLOW_SAID):
        d.clear()
    rows: list[dict] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, **kw: rows.append({"kind": kind, **(kw.get("extra") or {})}))
    monkeypatch.setattr("nucleo.dispatch._SESSIONS", {})
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    monkeypatch.setattr("nucleo.circuit.ledger.get", lambda uid: None)
    yield rows
    trace.adopt("")


def _of(rows, rule):
    return [r for r in rows if r.get("kind") == "owner" and r.get("rule") == rule]


# ── the label: a box no errand owns is the turn's, never «task-owned» ────────────────────────────────────────

def test_the_turns_pass_signs_its_show_by_who_owns_the_box(events, monkeypatch):
    from nucleo.acts import search_sheet
    shows: list[str] = []
    monkeypatch.setattr("nucleo.acts.canvas.apply", lambda op, wid, src, **kw: shows.append(src) or True)
    monkeypatch.setattr("widgets.results.data.apply_action", lambda *a, **k: {"ok": True})
    monkeypatch.setattr("widgets.results.data.begin_task", lambda *a, **k: None)
    monkeypatch.setattr("widgets.results.data.prune_sheets", lambda *a, **k: None)
    trace.adopt("T36·e339")
    search_sheet._write_sheet("b1-7", "4Runner", [], {}, inherited=False, delivered=False, asked=CAR_EN[0])
    assert shows == ["turn:T36·e339"], "a box no errand owns was signed as an errand's sheet"

    class Rec:
        uid, sheet, task_id = "b1-8", "b1-8", "8"
    monkeypatch.setattr("nucleo.dispatch._SESSIONS", {"8": Rec()})
    search_sheet._write_sheet("b1-8", "4Runner", [], {}, inherited=True, delivered=False, asked=CAR_EN[0])
    assert shows[-1] == "sheet:b1-8", "a live errand's own sheet lost its errand's signature"


@pytest.mark.parametrize("src, rule", [("turn:T36", "turn-owned"), ("sheet:b1-8", "task-owned"),
                                       ("worker:8", "task-owned")])
def test_the_arbiter_names_the_turn_apart_from_an_errand(src, rule):
    v = canvas_arbiter.decide("show", "results::b1-8", src)
    assert v.allow and v.rule == rule


# ── a discarded turn still acting ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("whole, tail", [CAR_EN, CAR_ES], ids=["car-en", "car-es"])
def test_a_discarded_turns_write_is_counted_in_either_order(events, whole, tail):
    trace.adopt("T37")
    so.on_write("b1-ls2", tail)               # the pass launched before the discard landed
    so.turn_discarded("T37")
    assert _of(events, "discarded_launch")[-1]["order"] == "before"
    so.on_show("results::b1-ls2", "turn:T37")  # …and the show 2.7 s after it
    assert len(_of(events, "discarded_launch")) == 2


def test_a_live_turn_launches_without_a_discard_mark(events):
    trace.adopt("T40")
    so.on_write("b1-9", FLAT_EN[0])
    so.errand_born(9, FLAT_EN[0], {"trace": "T40"})
    assert not _of(events, "discarded_launch")


# ── the errand's identity is the joined request, never its last fragment ─────────────────────────────────────

@pytest.mark.parametrize("whole, tail", [CAR_EN, CAR_ES, FLAT_EN], ids=["car-en", "car-es", "flat-en"])
def test_an_errand_named_after_a_fragment_is_counted(events, whole, tail):
    so.turn_joined("T39", whole)
    so.errand_born(5, tail, {"trace": "T39"})
    hit = _of(events, "fragment_goal")
    assert hit and hit[0]["id"] == "5" and hit[0]["allow"] is False
    events.clear()
    so.errand_born(6, whole, {"trace": "T39"})
    assert not _of(events, "fragment_goal"), "the joined request itself was counted as a fragment"


# ── two doors, one question ─────────────────────────────────────────────────────────────────────────────────

def test_the_flow_door_and_the_dispatcher_disagreeing_is_counted(events):
    trace.adopt("T39")
    so.flow_said("Okay.", "2")
    so.dispatcher_said({"trace": "T39"}, "Okay.", "", "miss")
    assert _of(events, "door_disagree")[0]["flow_of"] == "2"


@pytest.mark.parametrize("flow, into, ctx", [("2", "2", {}), ("esc:9", "9", {}), ("", "", {}),
                                             ("2", "", {"confirmed": True}), ("delivered:4", "", {})])
def test_agreeing_doors_count_nothing(events, flow, into, ctx):
    trace.adopt("T41")
    so.flow_said("the car, under fifty", flow)
    so.dispatcher_said({"trace": "T41", **ctx}, "the car, under fifty", into, "containment")
    assert not _of(events, "door_disagree")


# ── duplicates, non-owners, orphans ─────────────────────────────────────────────────────────────────────────

def test_a_second_sheet_for_the_same_joined_request_is_a_duplicate(events):
    trace.adopt("T36")
    so.turn_joined("T36", CAR_EN[0])
    so.on_write("b1-ls1", CAR_EN[0])
    trace.adopt("T37")
    so.turn_joined("T37", CAR_EN[0])
    so.on_write("b1-ls2", "Sorry.")           # the door read the fragment; the joined request is the same car
    assert _of(events, "duplicate_open")[0]["twin"] == "results::b1-ls1"


def test_two_different_requests_are_two_sheets_and_no_duplicate(events):
    trace.adopt("T50")
    so.on_write("b1-20", "find me a used Toyota 4Runner, thirty to fifty thousand")
    trace.adopt("T51")
    so.on_write("b1-21", "busca una guitarra acústica de segunda mano en Barcelona")
    assert not _of(events, "duplicate_open")


def test_a_turn_writing_an_errands_sheet_is_a_non_owner_and_his_hands_are_not(events, monkeypatch):
    class Rec:
        uid, sheet, task_id = "b1-8", "b1-8", "8"
    monkeypatch.setattr("nucleo.dispatch._SESSIONS", {"8": Rec()})
    monkeypatch.setattr("nucleo.dispatch.get_record", lambda ref: Rec() if str(ref) == "8" else None)
    trace.adopt("T42")
    so.on_write("b1-8", "the car, under forty")
    assert _of(events, "non_owner_write")[0]["owner"] == "errand:b1-8"
    so.on_show("results::b1-8", "user")
    so.on_show("results::b1-8", "worker:8")
    assert not _of(events, "non_owner_show"), "his hands or the errand's own worker were counted as non-owners"


def test_a_pass_that_neither_delivers_nor_hands_on_is_an_orphan(events, monkeypatch):
    from nucleo.acts import search_sheet
    monkeypatch.setattr("search.listing.search", lambda q: {"items": [], "sources": [], "needs_browser": True})
    monkeypatch.setattr(search_sheet, "_write_sheet", lambda *a, **k: None)
    monkeypatch.setattr(search_sheet, "_hand_on", lambda *a, **k: 0)     # the escalation was parked or refused
    out = search_sheet.fast_pass("Toyota 4Runner", sheet="b1-3")
    assert _of(events, "orphan")[0]["sheet"] == out["sheet"] == "b1-3"


def test_a_measurement_that_breaks_never_reaches_the_canvas(monkeypatch):
    from nucleo.acts import canvas
    monkeypatch.setattr(so, "_owner", lambda *a: 1 / 0)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    assert canvas.apply("show", "results::b1-9", src="user")


# ── the WIRING: the real doors report, not a helper called by hand ───────────────────────────────────────────

def test_a_discarded_turn_reports_through_the_real_discard(events, monkeypatch):
    from voice.engine.llm.providers import nucleo
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: "Sorry.")
    s = type("S", (), {})()
    s._llm, s._chat_ctx, s._phase, s._death_logged = type("B", (), {"_window": []})(), object(), "pre", False
    trace.adopt("T37")
    so.on_write("b1-ls2", "Sorry.")
    nucleo.NucleoLLMStream._note_death(s, "superseded")
    assert _of(events, "discarded_launch")


def test_the_flow_door_records_its_answer(events, monkeypatch):
    import asyncio
    from nucleo.turn import flow_of
    monkeypatch.setattr(flow_of, "candidates", lambda: [{"id": "2", "request": "I wanna buy a car. A new car.",
                                                         "parked": True}])
    trace.adopt("T39")
    asyncio.run(flow_of.flow_of("I wanna buy a car, a new 4Runner"))
    so.dispatcher_said({"trace": "T39"}, "Okay.", "", "miss")
    assert _of(events, "door_disagree"), "the flow door's answer never reached the comparison"


def test_an_escalation_reports_its_birth(events, monkeypatch):
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "_emit_bus", lambda *a, **k: None)
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    so.turn_joined("T39", CAR_ES[0])
    assert errand.escalate_to_slowbrain(CAR_ES[1], context={"trace": "T39", "kind": "web"})
    assert _of(events, "fragment_goal")


def test_the_dispatcher_reports_its_answer_through_the_real_listener(events, monkeypatch, tmp_path):
    import asyncio

    import bus
    from memory import db as memdb
    from nucleo import dispatch
    from nucleo.acts import errand
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")
    monkeypatch.setattr(dispatch, "_run_session", lambda task: asyncio.sleep(0))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    trace.adopt("T39")
    so.flow_said("Okay.", "2")

    async def run():
        bus.reset(); errand.reset()
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        errand.escalate_to_slowbrain("Okay, and a sunroof", context={"kind": "web", "trace": "T39"})
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); task.cancel()

    asyncio.run(run())
    dispatch._SESSIONS.clear()
    memdb.reset_db()
    assert _of(events, "door_disagree")[0]["dispatcher"] == ""


def test_the_admitted_turn_hands_its_joined_request_on(events, monkeypatch):
    import asyncio
    import types

    from nucleo.input import stt as acc
    from nucleo.turn import brief as tb
    from voice.engine.llm.providers import nucleo as _p, turn_admit
    monkeypatch.setattr(tb, "ask_for_turn", lambda text, **k: {"judged": text})
    monkeypatch.setattr(_p._show_target, "_running_goals", lambda: [])
    brain = types.SimpleNamespace(_acc=acc.Accumulator(), _window=[], _seeded=True)
    attention = types.SimpleNamespace(typed_line=lambda t: False, clamp_input=lambda t, n: (t, False))
    acc.unanswered_by(brain, CAR_EN[0])
    trace.adopt("T39")
    asyncio.run(turn_admit.admit_the_turn(attention=attention, brain=brain, emit=lambda *a, **k: None,
                                          first_turn=False, text=CAR_EN[1]))
    assert so.joined("T39").startswith(CAR_EN[0])
