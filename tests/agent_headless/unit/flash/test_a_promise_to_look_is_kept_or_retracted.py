"""V2-717 — a promise to LOOK is kept by a look, or retracted out loud; and a lens is never eaten as a drag.

## The measured incident

Session `c502d3ff`, 2026-09-17 20:57, the operator's own engine, in English.

| t | he said | the model | what ran |
|---|---|---|---|
| 55 s | «I think Ivan asked for something in Telegram» | `mensajeria:open {}` | opened — and SEALED as last data-op |
| 125 s | «Are you continuing the conversation?» | «Let me check your Telegram to see what Ivan asked.» + `mensajeria:open {}` | op eaten as context-bleed → **nothing** |
| 131 s | «…sending the email as he requested. Or not.» | «Let me open Telegram to see what Ivan asked about.» + same op | eaten → **nothing** |
| 171 s | «I don't think you're checking anything. Are you?» | «You're right to call that out, Richard. Let me actually open Telegram now…» + same op | eaten → **nothing** |
| 197 s | «Looks like you're ignoring my request.» | same op | the 120 s window had expired → ran |

The operator's rule: «si nos hace una petición la tenemos que resolver o cancelar o avisar al usuario, pero
nunca podemos dejar al aire las conversaciones, y menos cuando el agente nos dice específicamente que lo
estamos mirando».

Two mechanisms, each with its own section:

  1. `data_ops.is_context_bleed` — the V2-038 anti-drag guard, extracted and taught that a VIEW-op is never a
     drag. Its hatch is payload-word overlap and a lens carries an empty payload, so for `open`/`show_view`
     the hatch could never open, whatever the operator said. The guard stops duplicated WRITES; a lens writes
     nothing.
  2. `answer_guards.a_promise_left_hanging` + `second_pass.promise_repair` — a reply that promises a look
     on a turn that ran nothing is repaired by THE LOOK (the widget the promise names, read through the
     `read_widget` seam), and failing that by the deterministic retraction. Never air.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import asyncio
import time

import pytest

from i18n import langs
from nucleo.flash import answer_guards as ag, data_ops, second_pass as sp

# ── 1. A lens is never a drag ─────────────────────────────────────────────────────────────────────────────

SAID = "Are you continuing the conversation?"


def test_the_real_reemitted_open_is_not_bleed_because_it_is_a_lens():
    last = ("mensajeria", "open", {}, time.time() - 70)          # sealed at 55 s, re-emitted at 125 s
    assert data_ops.is_view_op("mensajeria", "open")
    assert not data_ops.is_context_bleed(last, "mensajeria", "open", {}, SAID)


@pytest.mark.parametrize("action", ["open", "show_view", "close"])
def test_every_declared_lens_of_the_messaging_widget_passes(action):
    last = ("mensajeria", action, {}, time.time() - 5)
    assert not data_ops.is_context_bleed(last, "mensajeria", action, {}, "again")


def test_the_v2_038_case_is_still_caught():
    """«borra el reloj» dragging the dentist's `add_meeting` — a duplicated WRITE, the guard's whole reason."""
    payload = {"title": "Dentista", "when": "2026-09-18 17:00"}
    last = ("agenda", "add_meeting", dict(payload), time.time() - 10)
    assert not data_ops.is_view_op("agenda", "add_meeting")
    assert data_ops.is_context_bleed(last, "agenda", "add_meeting", payload, "borra el reloj")


def test_the_hatches_of_the_write_guard_are_unchanged():
    payload = {"title": "Dentista", "when": "2026-09-18 17:00"}
    last = ("agenda", "add_meeting", dict(payload), time.time() - 10)
    # the sentence names the content → not a drag
    assert not data_ops.is_context_bleed(last, "agenda", "add_meeting", payload, "apunta otra vez lo del dentista")
    # the window expired → not a drag
    assert not data_ops.is_context_bleed(last, "agenda", "add_meeting", payload, "borra el reloj",
                                         now=last[3] + 121)
    # a different payload → not a drag
    assert not data_ops.is_context_bleed(last, "agenda", "add_meeting", {**payload, "title": "Óptica"}, "borra el reloj")


# ── 2. A promise to look, with no look behind it ──────────────────────────────────────────────────────────

REAL_PROMISES = [
    "Let me check your Telegram to see what Ivan asked.",                                          # 125 s
    "Let me open Telegram to see what Ivan asked about.",                                          # 131 s
    "You're right to call that out, Richard. Let me actually open Telegram now and check Ivan's conversation.",
    "Voy a mirar la agenda y te digo.",
    "Déjame que lo compruebe en los mensajes.",
    "Ahora mismo lo miro en el Telegram.",
    "I'll take a look at your calendar.",
]


@pytest.mark.parametrize("reply", REAL_PROMISES)
def test_a_promise_over_nothing_is_caught(reply):
    assert ag.a_promise_left_hanging(SAID, reply, acted=False, anything_running=False), reply


@pytest.mark.parametrize("reply", [
    "Ivan asked whether 9 PM Europe works for him — that's 12 PM Pacific.",   # an ANSWER
    "Shall I open Telegram and check?",                                        # a question, not a promise
    "Done.",
    "I've opened your Telegram — Ivan's last message is at the top.",         # past tense: it happened
    "The meeting is at 22:00.",
])
def test_a_healthy_reply_is_left_alone(reply):
    assert not ag.a_promise_left_hanging(SAID, reply, acted=False, anything_running=False), reply


def test_a_promise_kept_by_an_act_or_over_live_work_is_honest():
    p = REAL_PROMISES[0]
    assert not ag.a_promise_left_hanging(SAID, p, acted=True, anything_running=False)
    # live work covers a promise that could be ABOUT it — one naming no card we can read (demo pass 2026-09-28)…
    assert not ag.a_promise_left_hanging(SAID, "Let me look into the flights now.", acted=False, anything_running=True)
    # …while one that names a readable card is kept by reading it, worker or not (Z1: «Checking your agenda…»)
    assert ag.a_promise_left_hanging(SAID, p, acted=False, anything_running=True)


def test_the_repair_is_the_look_it_promised(monkeypatch):
    """«Let me check your Telegram…» names the messaging widget → the read route runs with HIS sentence as
    the question, and what comes back is the answer, not another promise."""
    from nucleo.flash import widget_read
    seen = {}

    async def _prepare(args, operator_text, lang_lock, emit, channel=""):
        seen.update(args=args, op=operator_text, channel=channel)
        return "SYS2"

    async def _collect(sys2, user_text, spec, max_tokens=240):
        assert sys2 == "SYS2"
        return "Ivan asked if 9 PM Europe works — that's noon Pacific."

    monkeypatch.setattr(widget_read, "prepare", _prepare)
    monkeypatch.setattr(sp, "collect", _collect)
    out = asyncio.run(sp.promise_repair(SAID, REAL_PROMISES[0], [], langs.spec("en"), lambda *a, **k: None,
                                        channel="voice"))
    assert seen["args"]["widget_id"] == "mensajeria"
    assert seen["args"]["question"] == SAID and seen["channel"] == "voice"
    assert "Ivan asked" in out


def test_with_nothing_readable_the_retraction_is_deterministic_and_in_both_languages(monkeypatch):
    """A promise that names no widget cannot be kept by a read — then the honest sentence, from the language
    table, never composed: the state (nothing running) is ours to say."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "resolve", lambda *_a, **_k: None)
    assert asyncio.run(sp.promise_repair("is it done?", "Let me check that now.", [], langs.spec("en"),
                                         lambda *a, **k: None)) == ""
    for code in ("es", "en"):
        rep = getattr(langs.spec(code), "promise_retracted", "")
        assert rep and len(rep.split()) <= 30, code
    assert _hollow(monkeypatch, langs.spec("en")) == ("Let me check that now. " + langs.spec("en").promise_retracted)


def _hollow(monkeypatch, spec):
    """The voice turn's one seam for hollow-turn repairs, with nothing running and nothing acted."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: False)
    return asyncio.run(sp.hollow_repairs("is it done?", "Let me check that now.", [], spec, did_act=False,
                                         covered=False, speak=lambda *_a: None, emit=lambda *a, **k: None))


def test_both_channels_carry_the_branch():
    """V2-252: the seam is shared, so the branch lives in it and not in one caller. The typed channel runs the
    voice turn (`nucleo.cli.turn.run_turn`), so the one seam is the one branch."""
    src = open("nucleo/flash/second_pass.py", encoding="utf-8").read()
    assert src.count("a_promise_left_hanging(") == 1, "the shared seam carries the branch exactly once"
    assert src.count("promise_repair(") >= 2        # the def + the seam's call


def test_an_identical_retry_of_a_refused_op_is_dropped_and_a_corrected_one_runs():
    """V2-773 (demo, images → markets): «Open the second one» reached `imagenes:select` with no item and was
    refused with the menu; the failure note asked for a re-call, and the next two turns («a chart of Apple
    stock», «the last month instead») re-emitted the identical empty `select` and spent their tools on a
    photo card. A refusal is not remembered as DONE (V2-707), so the anti-drag guard could not see it."""
    from nucleo.flash import data_ops as d
    d.remember_refusal("imagenes", "select", {})
    assert d.is_identical_retry_of_refused("imagenes", "select", {}, now=d._REFUSED["v"][3] + 5)
    assert not d.is_identical_retry_of_refused("imagenes", "select", {"item": "2"}), "the corrected call runs"
    assert not d.is_identical_retry_of_refused("markets", "show", {})
    assert not d.is_identical_retry_of_refused("imagenes", "select", {}, now=d._REFUSED["v"][3] + 400), "it expires"
    d._REFUSED["v"] = None
    assert not d.is_identical_retry_of_refused("imagenes", "select", {})
    import pathlib as _pl
    src = _vts.read(_pl.Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py")
    from nucleo.acts import card
    d.remember_refusal("imagenes", "select", {})
    lic = card.licence({"brief": None, "text": "the last month instead"}, "imagenes", "select", {}, at=card.FAST)
    assert (lic.verdict, lic.clause) == (card.DROP, "refused-again"), "the card door drops the identical re-send"
    d._REFUSED["v"] = None
    assert "_data_ops.remember_refusal(_w, _a, _p)" in src, "the seal must remember the refusal too"


# ── demo pass 2026-09-28, Z1 — «Checking your agenda for tomorrow…», nothing read, a trip worker running ──────

def test_the_progressive_form_is_a_promise_to_look():
    from nucleo.flash import answer_guards as ag
    assert ag.a_promise_left_hanging("what's on my plate tomorrow", "Checking your agenda for tomorrow…",
                                     acted=False, anything_running=False)
    assert not ag.a_promise_left_hanging("move it", "Checking… moved it to 2 PM.", acted=False,
                                         anything_running=False), "a claim of an act is not a promise to look"


def test_unrelated_live_work_does_not_cover_a_promise_that_names_a_card():
    """The trip worker was running; the promise was about the AGENDA — two turns later the model said «nothing on
    the calendar for tomorrow» over four meetings, because nothing had been read."""
    from nucleo.flash import answer_guards as ag
    assert ag.a_promise_left_hanging("x", "Checking your agenda for tomorrow…", acted=False, anything_running=True)
    assert not ag.a_promise_left_hanging("x", "Looking into the flights now.", acted=False, anything_running=True), \
        "a promise that names no readable card stays covered by the live errand"


def test_the_repair_is_spoken_as_a_separate_sentence_not_glued():
    """Demo pass 2026-09-28, C1/Z1: «Let me pull up your agenda for tomorrow.Tomorrow, Tuesday…» — the repair was
    sent as a delta right after the promise, and `speech.sanitize` strips a leading space, so the chat glued the
    two. The space goes AFTER sanitizing, and only when something was already said this turn."""
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py")
    i = src.index("_second.hollow_repairs(")
    call = src[i:i + 700]
    assert 'send((" " if (_sp or "").strip() else "")' in call, call
    from voice import speech
    assert speech.sanitize(" x", drop_metadata=False) == "x", "if sanitize stops stripping, this guard is moot"


def test_live_work_about_something_else_does_not_cover_a_promise(monkeypatch):
    """Demo pass 2026-09-28, Z1: «what's on my plate tomorrow» → «…let me look at Tuesday for you.», nothing read,
    the trip worker running; two turns later «Tuesday's clear — nothing booked» over four meetings."""
    from nucleo import dispatch
    from nucleo.flash import answer_guards as ag
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"request": "Plan a five-day warm trip from LAX for Anna and me, December 21 to 25, under 2000"}])
    assert ag.a_promise_left_hanging("what's on my plate tomorrow", "…let me look at Tuesday for you.",
                                     acted=False, anything_running=True)
    assert not ag.a_promise_left_hanging("how's the warm trip for anna going", "Let me look into the trip now.",
                                         acted=False, anything_running=True), "a promise about the live errand is covered"


def test_a_lens_that_repeats_the_last_one_changes_nothing():
    """Demo pass 2026-09-28, E2: «open the most important one» with the inbox already filtered; the verdict read
    `mensajeria:open` 0.97 and the model re-sent the identical `show_view {platform: email}`. Only a lens that
    REPEATS the card's last op yields to the verdict — V2-754's counter-case (a new `show_tab`) still runs."""
    import time as _t
    from nucleo.flash import data_ops as d
    last = ("mensajeria", "show_view", {"platform": "email", "window_h": 24}, _t.time() - 20)
    assert d.repeats_last_view(last, "mensajeria", "show_view", {"platform": "email"})
    assert not d.repeats_last_view(last, "mensajeria", "show_view", {"platform": "telegram"})
    assert not d.repeats_last_view(last, "youtube", "show_tab", {"tab": "home"})
    assert not d.repeats_last_view(("mensajeria", "show_view", {"platform": "email"}, _t.time() - 900),
                                   "mensajeria", "show_view", {"platform": "email"}), "an old lens is not a repeat"
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py")
    assert "_data_ops.repeats_last_view(brain._last_dataop, _cd[\"card\"], action_name, res.payload)" in src


class _ModelSpec:
    """What the LIVE voice turn hands the repairs: the model's spec, not a language table."""
    model = "deepseek-flash"


def test_the_retraction_sounds_with_the_spec_the_live_turn_passes(monkeypatch):
    """Demo pass 2026-09-28 (full13 Z1): «Let me check your day for tomorrow.» and then silence — the retraction
    was read as `getattr(spec, "promise_retracted", "")` off the MODEL spec the voice channel passes, which is
    always "". The sentence belongs to the operator's language table."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "resolve", lambda *_a, **_k: None)
    monkeypatch.setattr(sp, "_card_the_catalogue_names", lambda *_a, **_k: asyncio.sleep(0, ""))
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    out = _hollow(monkeypatch, _ModelSpec())
    assert out == "Let me check that now. " + langs.spec("en").promise_retracted


def test_a_promise_naming_no_card_reads_the_card_the_catalogue_names(monkeypatch):
    """Same turn: neither «what's on my plate tomorrow» nor «Let me check your day» says «calendar». Which card
    holds tomorrow is a question of meaning, asked of the catalogue reader — and the promise is kept by reading it."""
    from nucleo import jev
    from nucleo.flash import widget_read
    seen = {}
    monkeypatch.setattr(widget_read, "resolve", lambda *_a, **_k: None)
    monkeypatch.setattr(jev, "choose_sync", lambda *_a, **_k: {"choice": "agenda", "confidence": 0.93})

    async def _prepare(args, text, lock, emit, channel=""):
        seen["wid"] = args["widget_id"]
        return "SYS2"

    async def _collect(sys2, user_text, spec, max_tokens=240):
        return "Tomorrow you have the weekly review at 9 and the product meeting at 11."
    monkeypatch.setattr(widget_read, "prepare", _prepare)
    monkeypatch.setattr(sp, "collect", _collect)
    out = asyncio.run(sp.promise_repair("what's on my plate tomorrow", "Let me check your day for tomorrow.", [],
                                        _ModelSpec(), lambda *a, **k: None, channel="voice"))
    assert seen["wid"] == "agenda" and "weekly review" in out


def test_a_promise_that_names_two_cards_reads_the_one_his_words_are_about(monkeypatch):
    """Demo pass 38 (2026-09-29), Z1: «what's on my plate tomorrow» → «One moment — let me pull up your day and your
    messages for tomorrow.», nothing called. «pull up your day» was not read as a promise (only «pull THAT up»
    was), and the reply names the messages card by word — reading it would have answered with mail. His sentence
    is the order: the catalogue on HIS words decides, the reply's naming comes last."""
    from nucleo import jev
    from nucleo.flash import widget_read
    reply = "One moment — let me pull up your day and your messages for tomorrow."
    assert ag.a_promise_left_hanging("what's on my plate tomorrow", reply, acted=False, anything_running=False)
    seen = {}
    monkeypatch.setattr(jev, "choose_sync", lambda *_a, **_k: {"choice": "agenda", "confidence": 0.93})

    async def _prepare(args, text, lock, emit, channel=""):
        seen["wid"] = args["widget_id"]
        return "SYS2"

    async def _collect(sys2, user_text, spec, max_tokens=240):
        return "Tomorrow you have the weekly review at 9."
    monkeypatch.setattr(widget_read, "prepare", _prepare)
    monkeypatch.setattr(sp, "collect", _collect)
    asyncio.run(sp.promise_repair("what's on my plate tomorrow", reply, [], _ModelSpec(), lambda *a, **k: None,
                                  channel="voice"))
    assert seen["wid"] == "agenda", seen


def test_a_look_where_the_turn_asks_to_do_yields_to_the_verdict():
    """Demo pass 2026-09-28 (full15 E4): «oh and leave that inworld one as unread» — verdict `mensajeria:unread` at
    1.00, the model called `peek {n: 3}`. A look changes nothing; when the turn wants an act and the verdict names
    one that is not a look, the look yields. A model ACT over a verdict still runs (V2-754's counter-case)."""
    from nucleo.flash import data_ops as d
    assert d.is_view_op("mensajeria", "peek"), "peek reads and changes nothing"
    assert d.a_view_where_the_verdict_acts("mensajeria", "peek", "unread", "act")
    assert not d.a_view_where_the_verdict_acts("mensajeria", "peek", "unread", "tell"), "he asked to be told"
    assert not d.a_view_where_the_verdict_acts("youtube", "restart", "show_tab", "act"), "a model act is not a look"
    assert not d.a_view_where_the_verdict_acts("mensajeria", "show_view", "open", "act"), "a look over a look runs"
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py")
    assert "_data_ops.a_view_where_the_verdict_acts(_cd[\"card\"], action_name, _dis, _vw_words)" in src
