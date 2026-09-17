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


def test_the_provider_calls_the_extracted_predicate_and_keeps_no_copy():
    src = open("voice/engine/llm/providers/nucleo.py", encoding="utf-8").read()
    assert "_data_ops.is_context_bleed(" in src
    assert "(time.time() - _last[3]) < 120" not in src, "the inline copy of the rule must be gone"


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
    assert not ag.a_promise_left_hanging(SAID, p, acted=False, anything_running=True)


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
    assert asyncio.run(sp.probe_hollow_repairs("is it done?", "Let me check that now.", [], langs.spec("en"))) \
        == ("Let me check that now. " + langs.spec("en").promise_retracted)


def test_both_channels_carry_the_branch():
    """V2-252: the seam is shared, so the branch lives in it and not in one caller."""
    src = open("nucleo/flash/second_pass.py", encoding="utf-8").read()
    assert src.count("a_promise_left_hanging(") == 2, "voice and probe must both carry the branch"
    assert src.count("promise_repair(") >= 3        # the def + both callers
