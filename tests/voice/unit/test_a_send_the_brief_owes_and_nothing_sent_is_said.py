"""A turn the brief is SURE sends something in his name, where nothing that sends ran, says it sent nothing (node 2.958).

Demo sandbox 2026-10-29 (pass 2, C2-C4): «find me a free 45 minutes tomorrow afternoon to talk with rowan», «ok book it,
call it catch up with rowan», «actually move it half an hour later». Each turn's agenda op ran; each reply also
PROMISED a Telegram to Rowan («I'll check with Rowan on Telegram now», «the Telegram heads-up going out to him»), and
no message left — the brief's `errand_class` read `sends_for_him` all three times. The turn had acted, so no honest
line was owed, and he was left believing a message went out.

The mechanism reads the turn's FACTS and the verdict, never the reply: `promise_kept.unsent_line` says the i18n
`send_not_done` line when the verdict is sure and no op declaring `external.send` ran, no send door was reached, no
errand started, and no confirm this turn opened (his yes would be the send). The half that stops the brief from reading
«to talk with X» as an order to message X is the `errand_class` criterion (`nucleo/acts/errand._CLASSES`), measured by
the live bank cases `live-c2-*`, `live-c3-es-*` and `live-c5-es-*` in `tests/brain/cases/demo-live.json`.

Disarm: each of the four facts removed from `unsent_line` turns its case red; `say_after` not consulting it turns the
turn-end case red; the verdict not read turns the «none» case red.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo import consequence
from nucleo.acts import errand
from nucleo.turn import promise_kept as pk
from voice import trace
from widgets import confirm


def _brief(cls: str, conf: float = 0.9) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {errand.CLASS_KEY: {"choice": cls, "confidence": conf}}}


@pytest.fixture(autouse=True)
def _turn(monkeypatch):
    monkeypatch.setattr(confirm, "_PENDING", {})
    trace.begin("a turn", origin="turno")


@pytest.fixture(params=["en", "es"])
def lang(request, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", request.param)
    from i18n import langs
    line = langs.current_language().send_not_done
    assert line.strip()
    return line


def test_an_agenda_act_with_a_send_owed_and_none_sent_says_so(lang):
    for ops in ([("agenda", "find_free")], [("agenda", "add_meeting")], [("agenda", "move_meeting")], []):
        assert pk.unsent_line(_brief("sends_for_him"), ops) == lang


@pytest.mark.parametrize("ops", [[("mensajeria", "send_to")], [("agenda", "find_free"), ("agenda", "invite")]])
def test_an_op_that_sends_is_the_send(ops, lang):
    assert pk.unsent_line(_brief("sends_for_him"), ops) == ""


@pytest.mark.parametrize("door", ["messaging.tag", "cluster.send", "worker.spawn"])
def test_a_send_door_or_an_errand_reached_is_the_send(door, lang):
    assert consequence.passes(door)
    assert pk.unsent_line(_brief("sends_for_him"), [("agenda", "add_meeting")]) == ""


def test_a_confirm_this_turn_opened_asks_for_the_send(lang):
    confirm.request("data", "mensajeria", "Shall I send it?", op={"action": "send_to", "payload": {}}, notify_ui=False)
    assert pk.unsent_line(_brief("sends_for_him"), []) == ""


@pytest.mark.parametrize("brief", [_brief("none"), _brief("sends_for_him", conf=0.3), None])
def test_no_sure_send_verdict_owes_nothing(brief, lang):
    assert pk.unsent_line(brief, [("agenda", "find_free")]) == ""


def test_the_turn_end_says_it_after_an_act_that_ran(lang, monkeypatch):
    """`say_after` as the voice and text turns call it: the agenda op ran (`acted`), the send did not."""
    said: list[str] = []
    speech = SimpleNamespace(sanitize=lambda s, drop_metadata=True: s)
    window = [{"role": "assistant", "content": "Four to four forty-five — I'll check with Rowan on Telegram now."}]
    data_done = {"v": True, "ops": [("agenda", "find_free")]}
    out = pk.say_after(window[0]["content"], data_done, acted=True, send=said.append, speech=speech, window=window,
                       emit=lambda *a, **k: None, turn=(_brief("sends_for_him"), [], "find me 45 minutes", None))
    assert out == lang and said and lang in said[-1] and window[-1]["content"].endswith(lang)
    said.clear()
    assert pk.say_after("Done.", {"v": True, "ops": [("agenda", "find_free")]}, acted=True, send=said.append,
                        speech=speech, window=[], emit=lambda *a, **k: None,
                        turn=(_brief("none"), [], "find me 45 minutes", None)) == ""
    assert not said
