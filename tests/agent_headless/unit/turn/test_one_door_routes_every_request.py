"""One door routes every request, before anything is opened (V2-844 F2, 2026-11-02).

A car request dictated in fragments: the flow door said «this is the parked car» three times and was not obeyed
(no sheet to hand back); the dispatcher's dedup — the same judge, asked again 5 s later — said «new» for «Okay.»,
and the car's own confirmed relaunch was then folded INTO the errand called «Okay.». A turn discarded unanswered
still wrote its sheet. Two doors, one question, opposite answers, and nobody owning the result.

`flow_of.route` is now THE answer for a turn — begun beside the model call, read at the escalation portal and the
listing door before their first side effect: `conversation` (nothing to commission), a `list` (one sentence, several
errands), `inject|absorb|reopen|join|stop|steer|replace` into the flow it belongs to, or `new`. The dispatcher's dedup
stays behind it and folds AND warns when the door missed. A worker can hand words back (`not_mine`).
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from nucleo.acts import errand, surface_owner
from nucleo.dispatch import confirm
from nucleo.turn import brief_turn, flow_door, flow_of
from voice import trace

CAR_EN = ("let's focus on the car. I wanna... One of those big runners, a Toyota 4Runner. Two or three good offers. "
          "Thirty, forty, fifty thousand. Okay.", "Okay.")
CAR_ES = ("vale, el coche. Uno de esos todoterreno grandes, un Toyota 4Runner. Dos o tres buenas ofertas. Entre treinta "
          "y cincuenta mil. Vale.", "Vale.")
CAR_GOAL = {"en": "I wanna buy a car, a Toyota 4Runner", "es": "quiero comprarme un coche, un Toyota 4Runner"}


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    errand.reset()
    for d in (flow_of._TURN, surface_owner._DISCARDED, surface_owner._FLOW_SAID):
        d.clear()
    flow_of._NOT_MINE.clear()
    state = {"pool": [], "judge": "", "judged": 0, "bus": [], "relayed": [], "stop": None}
    monkeypatch.setattr(flow_of, "candidates", lambda: list(state["pool"]))

    def judge(text, live):
        state["judged"] += 1
        return state["judge"]
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", judge)
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: state["bus"].append(payload))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    monkeypatch.setattr("nucleo.dispatch.relay_his_words", lambda which, words: state["relayed"].append((which, words)) or True)
    monkeypatch.setattr("nucleo.request.stop.verdict", lambda brief: state["stop"])
    monkeypatch.setattr("voice.brain_notes.push", lambda *a, **k: None)
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    yield state
    trace.adopt("")
    errand.rows_settled()
    memdb.reset_db()
    errand.reset()


def _turn(t: str, judged: str) -> None:
    trace.adopt(t)
    brief_turn.remember_for_the_turn({"judged": judged})


def _escalate(t: str, judged: str, req: str, ctx: dict | None = None) -> int:
    """A turn as it runs: its route begun beside the model call, settled before the launch, then the portal."""
    async def turn():
        _turn(t, judged)
        flow_of.begin(judged)
        await flow_of.settled()
        return errand.escalate_to_slowbrain(req, context=dict(ctx or {}))
    return asyncio.run(turn())


def _parked(tid: str, request: str) -> dict:
    confirm._PENDING_CONFIRM[tid] = {"request": request, "question": "¿Lo hago?", "sheet": "", "context": {}}
    return {"id": tid, "request": request, "parked": True}


# ── the fragments of one request are that request's ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang, whole, tail", [("en", *CAR_EN), ("es", *CAR_ES)])
def test_a_fragment_of_a_parked_request_joins_it_and_opens_nothing(door, lang, whole, tail):
    door["pool"] = [_parked("2", CAR_GOAL[lang])]
    door["judge"] = "2"
    _turn("T39", whole)
    assert errand.escalate_to_slowbrain(tail, context={"src": "voice"}) == 0
    assert not door["bus"], "the fragment opened an errand of its own (the one called «Okay.»)"
    assert confirm._PENDING_CONFIRM["2"]["refinements"] == [whole], "the parked car never heard his whole request"


def test_a_flat_search_nobody_covers_is_a_new_errand_routed_new(door):
    _turn("T40", "find me a flat to rent in Madrid, two bedrooms, near Retiro")
    tid = errand.escalate_to_slowbrain("find me a flat to rent in Madrid, two bedrooms, near Retiro", context={})
    assert tid and door["bus"][0]["context"]["routed"] == "new:"


def test_two_different_requests_in_a_row_are_two_errands(door):
    _turn("T41", "find me a used Toyota 4Runner, thirty to fifty thousand")
    first = errand.escalate_to_slowbrain("find me a used Toyota 4Runner, thirty to fifty thousand", context={})
    door["pool"] = [{"id": str(first), "request": "find me a used Toyota 4Runner, thirty to fifty thousand"}]
    _turn("T42", "busca una guitarra acústica de segunda mano en Barcelona")
    second = errand.escalate_to_slowbrain("busca una guitarra acústica de segunda mano en Barcelona", context={})
    assert first and second and first != second and len(door["bus"]) == 2


# ── into a live errand: inject, steer, stop; into a finished one: reopen ─────────────────────────────────────

LIVE = {"id": "5", "request": "find me a used Toyota 4Runner, thirty to fifty thousand", "sheet": "b1-5"}


def test_a_refinement_reaches_the_live_errand_with_the_way_back(door):
    door["pool"], door["judge"] = [dict(LIVE)], "5"       # the model judge: a refinement that shares few words
    text = "the Toyota 4Runner, only diesel, under forty thousand"
    assert _escalate("T43", text, text) == 0
    which, words = door["relayed"][0]
    assert which == "5" and "not_mine" in words and not door["bus"]


def test_a_steer_reaches_it_and_a_stop_starts_nothing(door):
    door["pool"], door["judge"] = [dict(LIVE)], "5"
    door["stop"] = "steer"
    _escalate("T44", "the Toyota 4Runner — look on coches.net instead", "the Toyota 4Runner — look on coches.net instead")
    assert door["relayed"] and not door["bus"]
    door["stop"], door["relayed"] = "stop", []
    assert _escalate("T45", "stop the Toyota 4Runner search", "stop the Toyota 4Runner search") == 0
    assert not door["relayed"] and not door["bus"], "a stop launched or relayed the errand it stops"


def test_a_correction_on_a_finished_errand_reopens_into_its_sheet(door):
    door["pool"] = [{**LIVE, "id": "7", "sheet": "b1-7", "ended": True}]
    _turn("T46", "the Toyota 4Runner — exclude the red ones")
    errand.escalate_to_slowbrain("the Toyota 4Runner — exclude the red ones", context={})
    assert door["bus"][0]["context"]["sheet"] == "b1-7" and door["bus"][0]["context"]["routed"] == "reopen:7"


# ── conversation, several errands at once, a discarded turn ──────────────────────────────────────────────────

@pytest.mark.parametrize("said, kind", [("Okay.", "comment"), ("Vale.", "comment"), ("Sorry.", "comment"),
                                        ("Perdona, gracias.", "greeting")])
def test_a_word_after_a_request_is_conversation_not_an_errand(door, monkeypatch, said, kind):
    from nucleo.turn import brief as tb
    door["pool"] = [dict(LIVE)]
    # nothing cut before it: the turn's whole request is the word, and the verdict the turn pays reads it as chat
    monkeypatch.setattr(tb, "read", lambda h, key, d="", min_confidence=None:
                        (kind, {"confidence": 0.93, "used": True}) if key == tb.REQUEST_KEY else (d, None))
    assert _escalate("T47", said, said) == 0
    assert not door["bus"] and not door["relayed"]


def test_one_sentence_about_two_errands_routes_each_part(door):
    door["pool"] = [dict(LIVE), {"id": "6", "request": "book a table for two in Seville on Friday", "sheet": "b1-6"}]
    text = "The Toyota 4Runner under forty thousand. And the table in Seville, make it at nine."
    _turn("T48", text)
    r = asyncio.run(flow_of.route(text))
    assert r["as"] == flow_of.LIST and {p["flow"] for p in r["parts"]} == {"5", "6"}


def test_a_discarded_turn_starts_nothing_and_its_pass_writes_nothing(door, monkeypatch):
    from nucleo.acts import search_sheet
    wrote: list = []
    monkeypatch.setattr(search_sheet, "_write_sheet", lambda *a, **k: wrote.append(a))
    monkeypatch.setattr("search.listing.search", lambda q: {"items": [], "sources": [], "needs_browser": True})
    _turn("T37", CAR_EN[0])
    surface_owner.turn_discarded("T37")
    out = search_sheet.fast_pass("Toyota 4Runner", operator_text="Sorry.")
    assert not wrote and not out["escalated"] and not door["bus"], "a discarded turn still wrote, showed or launched"
    assert errand.escalate_to_slowbrain(CAR_EN[0], context={}) == 0


# ── the route runs once per turn, beside the model; the worker's last word undoes a fold ─────────────────────

def test_the_turns_route_is_begun_once_and_every_door_reads_it(door, monkeypatch):
    door["pool"], door["judge"] = [dict(LIVE)], "5"     # a refinement only the model judge can place
    text = "the Toyota 4Runner, only diesel, under forty thousand"

    async def _inject(which, words):
        return [which]
    monkeypatch.setattr("nucleo.dispatch.inject", _inject)

    async def turn():
        _turn("T49", text)
        flow_of.begin(text)                             # beside the model call
        joined = await flow_of.join(text)               # the listing door
        errand.escalate_to_slowbrain(text, context={})  # the portal, same turn
        return joined
    joined = asyncio.run(turn())
    assert joined.get("injected") and door["judged"] == 1, f"the judge ran {door['judged']} times for one turn"


def test_a_stop_that_lands_after_the_route_was_begun_still_holds(door):
    door["pool"], door["judge"] = [dict(LIVE)], "5"
    text = "the Toyota 4Runner search — drop it"

    async def turn():
        _turn("T52", text)
        flow_of.begin(text)
        await flow_of.settled()                         # routed before the verdict landed: «inject»
        door["stop"] = "stop"                           # …and the turn's stop verdict lands now
        return errand.escalate_to_slowbrain(text, context={})
    assert asyncio.run(turn()) == 0 and not door["relayed"] and not door["bus"]


@pytest.mark.parametrize("said", ["Okay.", "Vale."])
def test_a_door_outside_a_begun_route_still_reads_conversation(door, monkeypatch, said):
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda h, key, d="", min_confidence=None:
                        ("comment", {"confidence": 0.93, "used": True}) if key == tb.REQUEST_KEY else (d, None))
    _turn("T53", said)                                  # e.g. the promise backstop: no route was begun for it
    assert errand.escalate_to_slowbrain(said, context={}) == 0 and not door["bus"]


def test_words_a_worker_hands_back_become_their_own_errand_and_never_fold_there_again(door):
    from types import SimpleNamespace

    from nucleo.cli import worker_api_exec
    door["pool"] = [dict(LIVE)]
    words = "and the Toyota 4Runner insurance — get me quotes"
    out = worker_api_exec._not_mine({"words": words}, SimpleNamespace(task_id="5"))
    assert out["ok"] and door["bus"][0]["context"]["not_mine_of"] == "5"
    _turn("T50", words)
    assert flow_of.for_request(words)["as"] == flow_of.NEW, "the handed-back words folded into the same errand again"


# ── the dispatcher's dedup is a backstop: it folds, and warns when the door missed ───────────────────────────

def test_the_backstop_warns_only_when_the_door_did_not_route_it_there(door, monkeypatch):
    alerts: list = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: kind == "alert" and alerts.append(k["extra"]))
    assert flow_door.backstop("5", {"routed": "new:"}, "live")
    assert flow_door.backstop("5", {}, "parked")
    assert not flow_door.backstop("5", {"routed": "join:esc:5"}, "live")
    assert [a["how"] for a in alerts] == ["live", "parked"]


def test_the_portal_routes_only_a_turns_own_request(door):
    door["pool"] = [dict(LIVE)]
    trace.adopt("")                                     # no turn: the dispatcher decides, as it always did
    assert flow_door.at_the_portal("the Toyota 4Runner, only diesel", {}) is True
    _turn("T51", "the Toyota 4Runner, only diesel")
    for carried in ({"task_uid": "b1-5"}, {"confirmed": True}, {"born_uid": "b1-9"}, {"replaces": ["x"]}):
        assert flow_door.at_the_portal("the Toyota 4Runner, only diesel", dict(carried)) is True
