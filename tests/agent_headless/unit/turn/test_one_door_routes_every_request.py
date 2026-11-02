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
from nucleo.turn import brief_turn, flow_door, flow_of, turn_marks
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
    for d in (flow_of._TURN, surface_owner._FLOW_SAID):
        d.clear()
    turn_marks.reset()
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
    flow_of._TURN.clear()
    turn_marks.reset()
    trace.adopt("")
    errand.rows_settled()
    memdb.reset_db()
    errand.reset()


def _turn(t: str, judged: str, tail: str = "") -> None:
    trace.adopt(t)
    brief_turn.remember_for_the_turn({"judged": judged})
    if tail:
        turn_marks.cut(t, judged, tail)            # a cut sentence was joined in front of his tail


def _escalate(t: str, judged: str, req: str, ctx: dict | None = None, *, tail: str = "") -> int:
    """A turn as it runs: its route begun beside the model call, settled before the launch, then the portal."""
    async def turn():
        _turn(t, judged, tail)
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
    assert _escalate("T39", whole, tail, {"src": "voice"}, tail=tail) == 0
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
    door["pool"], door["judge"] = [{**LIVE, "id": "7", "sheet": "b1-7", "ended": True}], "7"
    _escalate("T46", "the Toyota 4Runner — exclude the red ones", "the Toyota 4Runner — exclude the red ones")
    assert door["bus"][0]["context"]["sheet"] == "b1-7" and door["bus"][0]["context"]["routed"] == "reopen:7"


# ── conversation, several errands at once, a discarded turn ──────────────────────────────────────────────────

def _reads_as(monkeypatch, kind: str) -> list:
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda h, key, d="", min_confidence=None:
                        (kind, {"confidence": 0.93, "used": True}) if key == tb.REQUEST_KEY else (d, None))
    notes: list = []
    monkeypatch.setattr("voice.brain_notes.push", lambda text, *a, **k: notes.append(text))
    return notes


@pytest.mark.parametrize("said, kind", [("Okay.", "comment"), ("Vale.", "comment"), ("Sorry.", "comment"),
                                        ("Perdona, gracias.", "greeting")])
def test_a_word_after_a_request_is_conversation_not_an_errand(door, monkeypatch, said, kind):
    notes = _reads_as(monkeypatch, kind)
    door["pool"] = [dict(LIVE)]        # the judge: no flow claims it (nothing cut before it, chat by the paid verdict)
    assert _escalate("T47", said, said) == 0
    assert notes and "no has abierto nada" in notes[-1], "the dropped escalation was a mute 0 the model never read"
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
    _turn("T37", CAR_EN[0], "Sorry.")
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


@pytest.mark.parametrize("said", ["those are too expensive, under thirty thousand",
                                  "esos son demasiado caros, por debajo de treinta mil"])
def test_a_comment_with_content_finds_its_flow_and_reaches_it(door, monkeypatch, said):
    _reads_as(monkeypatch, "comment")
    door["pool"], door["judge"] = [dict(LIVE)], "5"
    assert _escalate("T53", said, said) == 0
    assert door["relayed"] and door["relayed"][0][0] == "5", "a refinement read as a comment was swallowed"


@pytest.mark.parametrize("said", ["...", "¡Ok!", "Eh."])
def test_words_with_no_content_at_all_are_conversation_even_without_a_route(door, said):
    _turn("T54", said)                                  # e.g. a backstop's launch: no route was begun for it
    assert errand.escalate_to_slowbrain(said, context={}) == 0 and not door["bus"]


def test_a_chat_verdict_alone_never_drops_a_request_no_route_was_judged_for(door, monkeypatch):
    _reads_as(monkeypatch, "comment")
    door["pool"] = [dict(LIVE)]
    _turn("T55", "Okay.")                               # no begun route: the judge never ran — the dispatcher decides
    assert errand.escalate_to_slowbrain("Okay.", context={}) and door["bus"]


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


# ── B1 · one request of several is its own errand; a request with content of its own keeps its words ────────────

@pytest.mark.parametrize("cut, parts", [
    ("Pídeme cita con el dentista el martes y búscame un hotel en Roma para el viernes",
     ["Pídeme cita con el dentista el martes", "búscame un hotel en Roma para el viernes"]),
    ("Book me a dentist for Tuesday and find me a hotel in Rome for Friday",
     ["Book me a dentist for Tuesday", "find me a hotel in Rome for Friday"])])
def test_two_requests_in_one_turn_are_two_errands_each_with_its_own_text(door, cut, parts):
    async def turn():
        _turn("T60", cut, parts[1])               # even when the turn arrived cut
        flow_of.begin(cut)
        await flow_of.settled()
        errand.escalate_to_slowbrain(parts[0], context={"part": 0})
        errand.escalate_to_slowbrain(parts[1], context={"part": 1})
    asyncio.run(turn())
    assert [p["request"] for p in door["bus"]] == parts, "the parts became the whole sentence"


def test_an_inline_part_never_reaches_the_worker_of_the_escalated_one(door):
    whole = "find me flights to Rome next week, and remind me to call mum tonight"
    _escalate("T61", whole, "find me flights to Rome next week", tail="and remind me to call mum tonight")
    assert [p["request"] for p in door["bus"]] == ["find me flights to Rome next week"]


# ── B2 · in a list, each escalation is paired with its part by identity, through the portal ────────────────

def test_each_part_of_a_list_turn_reaches_its_own_errand_through_the_portal(door):
    door["pool"] = [dict(LIVE), {"id": "6", "request": "book a table for two in Seville on Friday", "sheet": "b1-6"}]
    text = "The Toyota 4Runner under forty thousand. And the table in Seville, make it at nine."

    async def turn():
        _turn("T62", text)
        flow_of.begin(text)
        r = await flow_of.settled()
        for i, p in enumerate(r["parts"]):
            errand.escalate_to_slowbrain(p["words"], context={"part": i})
        errand.escalate_to_slowbrain("book a flight to Lisbon on Monday", context={"part": 9})
    asyncio.run(turn())
    assert sorted(w for w, _m in door["relayed"]) == ["5", "6"], f"parts went to {door['relayed']}"
    assert [p["request"] for p in door["bus"]] == ["book a flight to Lisbon on Monday"]


# ── M2 · a likeness only proposes a finished or parked errand: the judge decides ─────────────────────────────

@pytest.mark.parametrize("done, asked", [("find me a hotel in Rome for Friday", "find me a hotel in Paris for Friday"),
                                         ("búscame un hotel en Roma para el viernes",
                                          "búscame un hotel en París para el viernes")])
def test_a_new_hotel_city_is_a_new_errand_not_a_reopen(door, done, asked):
    door["pool"] = [{"id": "8", "request": done, "sheet": "b1-8", "ended": True}]
    door["judge"] = ""                                   # the judge: a different stay
    _escalate("T63", asked, asked)
    assert door["bus"][0]["context"]["routed"] == "new:" and "sheet" not in door["bus"][0]["context"]


# ── m · the portal and the listing door ────────────────────────────────────────────────────────────────────

def test_an_outcome_the_portal_does_not_know_opens_the_errand(door, monkeypatch):
    monkeypatch.setattr(flow_of, "for_request", lambda *a, **k: {"as": "someday", "text": "x"})
    _turn("T64", "find me a flat in Madrid")
    assert flow_door.at_the_portal("find me a flat in Madrid", {}) is True


def test_a_stop_at_the_listing_door_says_stopped_and_injects_nothing(door, monkeypatch):
    door["pool"], door["judge"], door["stop"] = [dict(LIVE)], "5", "stop"
    injected: list = []

    async def _inject(which, words):
        injected.append(which)
        return [which]
    monkeypatch.setattr("nucleo.dispatch.inject", _inject)
    _turn("T65", "the Toyota 4Runner search — drop it")
    out = asyncio.run(flow_of.join("the Toyota 4Runner search — drop it"))
    assert out.get("stopped") and not out.get("injected") and not injected


def test_the_models_own_words_for_a_turn_nothing_was_cut_from_stay_its_own(door):
    said = "I need a dentist on Tuesday, and find me a hotel in Rome"
    _escalate("T66", said, "find me a hotel in Rome")          # no cut: the judged sentence is not a joined one
    assert [p["request"] for p in door["bus"]] == ["find me a hotel in Rome"]


def test_a_part_never_takes_the_route_of_the_whole_turn(door):
    door["pool"], door["judge"] = [dict(LIVE)], "5"            # the whole sentence is judged about the live 4Runner
    text = "the Toyota 4Runner under forty thousand, and book me a flight to Lisbon on Monday"

    async def turn():
        _turn("T67", text)
        flow_of.begin(text)
        await flow_of.settled()
        errand.escalate_to_slowbrain("book me a flight to Lisbon on Monday", context={"part": 1})
    asyncio.run(turn())
    assert [p["request"] for p in door["bus"]] == ["book me a flight to Lisbon on Monday"] and not door["relayed"]


def test_a_list_part_is_found_by_its_words_not_by_likeness(door):
    door["pool"] = [dict(LIVE), {"id": "6", "request": "book a table for two in Seville on Friday", "sheet": "b1-6"}]
    route = {"as": flow_of.LIST, "text": "x", "parts": [
        {"as": "inject", "flow": "5", "sheet": "b1-5", "words": "the Toyota 4Runner offers and the Seville table"},
        {"as": "inject", "flow": "6", "sheet": "b1-6", "words": "the Seville table"}]}

    async def turn():
        _turn("T68", "x")
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(route)
        flow_of._TURN["T68"] = fut
        return flow_of.for_request("the Seville table")
    assert asyncio.run(turn())["flow"] == "6", "the part was matched to the first one it resembles"
