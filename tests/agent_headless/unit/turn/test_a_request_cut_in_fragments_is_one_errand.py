"""A request dictated in fragments is ONE errand, ONE sheet, with the WHOLE request — the chain, end to end (V2-844).

The measured chain (2026-11-02): «I wanna buy a car. A new car.» parked on his yes (it moves money). He went on in
fragments — a long sentence his own barge-in cut, then «Sorry.», then «Okay.». Each turn ran the listing door and
the model escalated, three sheets opened, the dispatcher folded launches into one another, and the errand that
survived was called «Okay.».

Here the same chain runs through the real doors — the listing door, the escalation portal and the real dispatcher
listener — with the model's judge as a fake that answers what the measured one answered («this is the parked car»).
After his yes there is exactly one errand, its request carries his whole sentence, and no fast pass opened a box.
"""
from __future__ import annotations

import asyncio
import time

import pytest

import bus
from memory import db as memdb
from nucleo import dispatch
from nucleo.acts import errand, search_listing
from nucleo.dispatch import confirm
from nucleo.turn import brief_turn, flow_of, turn_marks
from voice import trace

CHAINS = {
    "en": ("I wanna buy a car. A new car.",
           "let's focus on the car. I wanna... One of those big runners. Kind of fourth renter, a Toyota 4Runner. Two "
           "or three good offers. Thirty, forty, fifty thousand.", "Sorry.", "Okay."),
    "es": ("Quiero comprarme un coche. Un coche nuevo.",
           "vale, centrémonos en el coche. Uno de esos todoterreno grandes, un Toyota 4Runner. Dos o tres buenas "
           "ofertas. Entre treinta y cincuenta mil.", "Perdona.", "Vale."),
}


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    errand.reset()
    turn_marks.reset()
    flow_of._TURN.clear()
    dispatch._SESSIONS.clear()
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    seen = {"passes": [], "sheets": [], "judge": []}

    def judge(text, live):                       # the measured judge: every fragment is about the parked car
        seen["judge"].append(text)
        return next((i for i, _r in live if i == "2"), "")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", judge)
    monkeypatch.setattr(dispatch, "about_a_live_errand", judge)
    monkeypatch.setattr(search_listing, "fast_pass", lambda q, **kw: seen["passes"].append(kw) or {})
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr(dispatch, "_run_session", lambda task: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_name_errand", lambda rec: None)
    monkeypatch.setattr(dispatch, "_sheet_open", lambda rec, **k: seen["sheets"].append(rec.task_id))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    yield seen
    errand.rows_settled()
    dispatch._SESSIONS.clear()
    flow_of._TURN.clear()
    turn_marks.reset()
    trace.adopt("")
    memdb.reset_db()


async def _turn(t: str, said: str, whole: str, *, cut: bool, discarded: bool = False) -> None:
    """One voice turn: admitted (cut or not), its route begun, the listing door, the model's escalation, then — if
    his next words barged in — discarded."""
    trace.adopt(t)
    brief_turn.remember_for_the_turn({"judged": whole})
    if cut:
        turn_marks.cut(t, whole, said)
    flow_of.begin(whole)
    await search_listing.listings({"text": said}, {"query": "Toyota 4Runner"})
    await flow_of.settled()
    errand.escalate_to_slowbrain(said, context={"src": "voice", "surface": "lista"})
    if discarded:
        turn_marks.discarded(t)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_car_dictated_in_fragments_is_one_errand_with_the_whole_request(engine, lang):
    first, long, sorry, okay = CHAINS[lang]
    confirm._PENDING_CONFIRM["2"] = {"request": first, "kind": "web", "trusted": True, "context": {},
                                     "question": "This moves money — shall I?", "sheet": "", "ts": time.time()}

    async def chain():
        bus.reset()
        stop = asyncio.Event()
        listener = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        await _turn("T36", long, long, cut=False, discarded=True)
        await _turn("T37", sorry, f"{long} {sorry}", cut=True, discarded=True)
        await _turn("T39", okay, f"{long} {sorry} {okay}", cut=True)
        await asyncio.sleep(0.1)
        engine["refinements"] = list(confirm._PENDING_CONFIRM["2"].get("refinements") or [])
        confirm.resolve_confirm(True, "2")           # his yes
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); listener.cancel()
    asyncio.run(chain())
    recs = list(dispatch._SESSIONS.values())
    assert not engine["passes"], "a fragment ran a fast pass of its own (and opened a box)"
    assert len(recs) == 1, f"{len(recs)} errands for one request: {[r.goal for r in recs]}"
    assert "4Runner" in recs[0].goal, f"the errand is called «{recs[0].goal[:80]}»"
    assert len(engine["sheets"]) <= 1, f"{len(engine['sheets'])} sheets for one errand"
    assert all("4Runner" in r for r in engine["refinements"]), \
        f"a bare fragment reached the errand as his words: {engine['refinements']}"
