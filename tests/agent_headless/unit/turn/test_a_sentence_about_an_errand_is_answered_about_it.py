"""A sentence about ONE of his errands is answered about that errand (three-tasks-at-once, rounds of 2026-10-10 20:00).

Measured on the probe channel, ES and EN, with a report, a monitor hunt and a game ordered in one breath:

  · ES — four long turns about the three live errands («del coche, ¿qué tal de autonomía real? ¿Y el juego? …») were
    taken by the LIST lane as new lists: each got «Entendido, me pides varias cosas. Me pongo con ellas y te aviso
    cuando termine», word for word, twice after he complained, and none of the questions was answered.
  · ES — «del informe quítame los híbridos» got «dame un momento» plus three MONITOR candidates.
  · EN — «but the jump, did you actually make it higher?» got the report's and the monitor's phases three times, in
    the engine's Spanish («Investigando…: entrando en ebay.es»), never a word about the game.
  · EN — «ah no those are all too small — the monitor…» cancelled the PARKED game: its «no» was about the listings.
  · EN — «stop it and try another way, yeah» stopped the worker, and the reply asked the same stop-or-wait question
    again, «4 min» for «3 min».

Every door below reads the same yardstick: which errands does the sentence NAME (`nucleo/turn/named_errand.py`).
"""
from __future__ import annotations

import asyncio
import threading
import time
import types

import pytest

from nucleo import batch, dispatch
from nucleo import dispatch_confirm as dc
from nucleo.turn import confirm_gates as gates
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import named_errand

REPORT = {"id": "1", "request": "Hazme un informe sobre coches eléctricos para ciudad", "phase": "leyendo material",
          "waiting_on": ""}
MONITOR = {"id": "3", "request": "Find real marketplace listings for: cheap used monitor (condition: used)",
           "phase": "entrando en ebay.es", "waiting_on": ""}
GAME = "Móntame un widget de un juego de plataformas tipo Super Mario"
# ES, the round's second canned turn, verbatim: three errands named, five sentences, just over the shape floor.
ES_TALK = ("Oye, ¿y la autonomía real del informe? Que te la ibas a leer y al final nada, te fuiste por los monitores. "
           "Dime eso, que es lo que me interesa. Y del monitor, si el Acer o el Samsung están bien, dime cuál es y lo "
           "dejamos. Del juego, avísame cuando lo tenga ya, que quiero probarlo.")


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def errands(monkeypatch):
    """The report and the monitor live; the game parked on «shall I build it?» with his refinement absorbed."""
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="Investigando…"))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"9": {
        "request": GAME, "kind": "code", "trusted": True, "context": {}, "sheet": "", "ts": time.time(),
        "question": "If I've got this right, you're asking me to BUILD you a new card. Shall I?",
        "refinements": ["sweet. btw on the game one, can you make the jump a bit higher?"]}})
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain", lambda req, context=None: 1)


# ── the yardstick ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_sentence_names_every_errand_it_talks_about(errands):
    assert {e["id"] for e in named_errand.named(ES_TALK)} == {"1", "3", "9"}
    assert [e["id"] for e in named_errand.named("but the jump, did you actually make it higher?")] == ["9"]
    assert named_errand.named("ok cool, thanks") == []
    assert all(not e["label"] for e in named_errand.known()), "«Investigando…» is a placeholder, not a label"


# ── 1. the canned receipt: never twice, never to a conversation about live work ─────────────────────────────
def test_a_long_message_about_errands_under_way_is_not_a_new_list(errands, monkeypatch):
    from nucleo.batch import detect
    assert detect.could_be_a_list(ES_TALK), "the case must reach the lane, or this test proves nothing"
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "several", "confidence": 0.99})
    started = []

    async def fake_start(text, **kw):
        started.append(text)
    monkeypatch.setattr(batch, "start", fake_start)
    assert asyncio.run(batch.intake(ES_TALK, origin="chat")) is None and not started
    numbered = "Apúntame esto:\n1. " + "\n2. ".join(["el informe del coche", "otro monitor", "el juego"]) + "\n3. x"
    numbered += " " + "y más detalles " * 30
    assert asyncio.run(batch.intake(numbered, origin="chat")), "an enumerated paste is still a list"


def test_with_nothing_under_way_the_same_message_is_still_a_list(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "several", "confidence": 0.99})

    async def fake_start(text, **kw):
        return "lista:x"
    monkeypatch.setattr(batch, "start", fake_start)

    async def _go():
        got = await batch.intake(ES_TALK, origin="chat")
        await asyncio.sleep(0)
        return got
    assert asyncio.run(_go()) == {"ack": batch.ack()}


def test_the_receipt_is_a_line_said_once(monkeypatch):
    from i18n import langs
    lang = langs.current_language()
    assert batch.receipt([]) == lang.list_started
    assert batch.receipt(["Hola.", lang.list_started]) == lang.list_started_again != lang.list_started
    assert batch.receipt([lang.list_started, lang.list_started_again]) == ""
    assert batch.assistant_lines([{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]) == ["y"]


def test_both_channels_hand_the_lane_what_was_already_said():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[4]
    assert "said=batch.assistant_lines(sess.window)" in (root / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "said=batch.assistant_lines(brain._window)" in (
        root / "voice/engine/llm/providers/fast_lane.py").read_text(encoding="utf-8")


# ── 2. a status question that names an errand ───────────────────────────────────────────────────────────────
def test_a_status_question_about_the_game_is_answered_about_the_game(errands, monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    line = E.status_owed("but the jump, did you actually make it higher? I keep asking lol",
                         _brief(wants_words="tell", request_type="question"))
    assert "Super Mario" in line and "monitor" not in line and "informe" not in line, line
    assert "entrando en" not in line and "Investigando" not in line, "no engine Spanish in an English line"


def test_a_question_about_everything_still_gets_everything(errands):
    line = E.status_owed("¿Cómo va todo?", _brief(wants_words="tell", request_type="question"))
    assert "informe" in line and "monitor" in line


# ── 3. an offer he answered is not asked again; a stop is said as done ──────────────────────────────────────
def test_the_stop_offer_is_made_once(monkeypatch):
    from nucleo.flash import delivery, live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: (GAME, 3, "sin avanzar"))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    first = delivery.apply_to_reply("Alright, give me a moment to look into that.", [])
    assert "stop it and try another way" in first
    again = delivery.apply_to_reply("Alright, give me a moment to look into that.", [])
    assert "stop it" not in again, "he already answered that offer"


def test_a_stop_he_ordered_is_said_as_done(monkeypatch):
    from i18n import langs
    from nucleo.flash import probe_after as PA
    out = asyncio.run(PA.the_words_it_owes(
        _hw=True, _parts=None, _show_chose=None, action="stop_worker", images_req=None,
        return_extra_exec={"executed": "stop"}, sess=types.SimpleNamespace(window=[]), spoken="", tags=[],
        text="stop it and try another way, yeah. no point waiting forever.", video_req=None,
        brief=_brief(wants_words="act", request_type="order")))
    assert out["spoken"] == langs.current_language().worker_stopped


# ── 4. a refinement of one errand does not get another errand's rows ────────────────────────────────────────
def test_the_rows_of_another_errand_are_not_glued_to_a_refinement(errands, monkeypatch):
    from nucleo.flash import delivery, live_blocks
    rows = ["Monitor Fujitsu Display P27-8 TE — 59", "HP EliteDisplay E243d 23,8 — 79.9", "Monitor LCD 22 — 55"]
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (MONITOR["request"], list(rows)))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    held = delivery.apply_to_reply("Vale, dame un momento que lo miro.", [],
                                   heard_now="Marco. Y ya que estás, del informe quítame los híbridos.")
    assert "Fujitsu" not in held, held
    asked = delivery.apply_to_reply("Vale, dame un momento que lo miro.", [],
                                    heard_now="¿Y del monitor tienes ya algo de 27?")
    assert "Fujitsu" in asked, "a sentence about THAT errand still gets its rows"


# ── 5. a «no» about the monitor does not cancel the parked game ─────────────────────────────────────────────
def test_a_no_about_another_errand_leaves_the_parked_one_waiting(errands, monkeypatch):
    from widgets import confirm as wconfirm
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(MONITOR)])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"9": {**dc._PENDING_CONFIRM["9"], "refinements": []}})
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: "no")     # even a judge that reads «no»
    ans = gates.resolve_all("ah no those are all too small — the monitor needs to be at least 27 inches, used is "
                            "fine, $150 max.", brief=_brief(request_type="answer"))
    assert not ans and "9" in dc._PENDING_CONFIRM
    assert gates.resolve_all("No, leave it").yes is False, "a plain no still answers at once"
