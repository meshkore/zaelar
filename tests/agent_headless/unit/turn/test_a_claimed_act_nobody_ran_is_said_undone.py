"""A claimed act nobody ran is said undone (CRIT-V12, `nucleo/turn/unserved`).

Measured in the use-case battery of 2026-11-06, ES and US, agenda and screen: «Cambio el aviso a las doce…» over an
`agenda:set_reminder` call the engine diverted and never ran; «I've cancelled just next Tuesday's piano» and «I've
cleared it» with ZERO calls. The mouth composes the turn's line from the acts that RAN, so an act that reached no door
had no verdict and the narration stood. Now the verdict is `unmet`, always said after the model's words: a model call
on a card no door of the turn touched, or a sure order aimed at a card or the canvas that no door served.

Disarm: make `unserved.outcomes` return [] (or `calls_not_run` return []) and the first two tests go red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus
from nucleo.circuit import verdict as V
from nucleo.turn import brief as tb, reply, unserved, verdicts

SP = type("S", (), {"sanitize": staticmethod(lambda t, **_: t)})


class _Done:
    def __init__(self, res):
        self._r = res

    def done(self):
        return True

    def cancelled(self):
        return False

    def result(self):
        return self._r


OK = {"ok": True, "result": {"title": "x"}}


@pytest.fixture
def turn(monkeypatch):
    """The brief as a dict of verdicts; no card acts; every manifest action reads as an act (never a read)."""
    v: dict = {}

    def read(h, key, fb, min_confidence=None):
        floor = verdicts.LICENCE if min_confidence is None else min_confidence
        t = v.get(key)
        return t if t and t[1]["confidence"] >= floor else (fb, None)
    monkeypatch.setattr(verdicts, "read", read)
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [])
    monkeypatch.setattr("nucleo.turn.brief_turn.of_this_turn", lambda: {})
    monkeypatch.setattr("widgets.effects.carries", lambda card, action, effect: False)
    reply._NOTED.clear()
    reply._ASKED.clear()
    return v


def _say(said, *, calls=(), tasks=(), quiet=True, held=False):
    out: list[str] = []
    text = asyncio.run(reply.after_acts(list(tasks), said, out.append, SP, model_calls=list(calls), quiet=quiet,
                                        held=held))
    return text, [o.strip() for o in out]


def _call(card, action, **payload):
    return {"name": "widget_data", "args": {"widget_id": card, "action": action, "payload": payload}}


ORDER = {"request_type": ("order", {"confidence": 0.84}), "wants_words": ("act", {"confidence": 0.78})}


@pytest.mark.parametrize("lang, said, card", [
    ("es", "Cambio el aviso a las doce del mediodía del día 16.", "agenda"),
    ("en", "Moving the training one ahead of the insane one.", "youtube"),
])
def test_a_model_call_no_door_ran_is_said_undone_naming_the_card(turn, monkeypatch, lang, said, card):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    from nucleo.flash import card_receipt
    name = card_receipt.card_name(card)
    text, out = _say(said, calls=[_call(card, "set_reminder" if card == "agenda" else "move")], quiet=True)
    assert out == [langs.current_language().reply_not_run.format(cards=name)], out
    assert text.startswith(said) and name in text


@pytest.mark.parametrize("lang, said, lean", [
    ("en", "Nothing's on screen to exit from — but I've cleared it, so you're at an empty canvas now.",
     ("canvas", "exit_fullscreen", 1.0)),
    ("es", "Hecho, te he quitado la clase del martes que viene.", (tb.CATALOG_KEY, "agenda", 0.93)),
    ("en", "Sure — I've cancelled just next Tuesday's piano with Abril.", (tb.TARGET_KEY, "agenda:cancel_meeting", 0.6)),
])
def test_a_sure_order_about_a_card_with_no_call_and_nothing_run_is_said_undone(turn, monkeypatch, lang, said, lean):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    turn.update(ORDER)
    key, choice, conf = lean
    turn[key] = (choice, {"confidence": conf})
    text, out = _say(said, calls=[], quiet=True)
    assert out == [langs.current_language().reply_nothing_done], out
    assert text.startswith(said)


def test_a_card_that_acted_this_turn_owes_nothing_for_the_call(turn):
    """The verdict completed or replaced the call on that card (CRIT-K2): no «not done» beside a landed op."""
    _t, out = _say("Done.", calls=[_call("youtube", "move")], tasks=[("youtube::remove", _Done(OK))], quiet=False)
    assert not any("YouTube" in o for o in out), out
    assert unserved.calls_not_run([_call("agenda", "set_reminder")], [("agenda::add_meeting", _Done(OK))]) == []
    assert unserved.calls_not_run([_call("agenda", "set_reminder")], []) == [("agenda", "set_reminder")]


@pytest.mark.parametrize("said, calls, quiet, held, brief", [
    ("¿A qué hora lo pongo?", [_call("agenda", "set_reminder")], True, False, {}),          # the turn ends asking him
    ("Cambio el aviso.", [_call("agenda", "set_reminder")], True, True, {}),                  # an act held for his yes
    ("Anotado: nada con gluten para ti.", [], True, False,
     {"request_type": ("comment", {"confidence": 0.92}), "wants_words": ("act", {"confidence": 0.56}),
      tb.CATALOG_KEY: ("none", {"confidence": 0.92})}),                                      # a comment, not an order
    ("It's up on your screen now.", [], True, False,
     {"request_type": ("comment", {"confidence": 0.3}), "wants_words": ("tell", {"confidence": 0.6})}),
    ("Tuesday you have piano at three.", [], True, False,
     {**ORDER, "wants_words": ("tell", {"confidence": 0.9}), tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}),
    ("Remember it, no gluten.", [], True, False, dict(ORDER)),                               # an order aimed at no card
    ("Done.", [{"name": "recall", "args": {}}], True, False,
     {**ORDER, tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}),                           # the model called something
    ("Done.", [], False, False, {**ORDER, tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}), # a door of the turn ran
])
def test_nothing_is_said_undone_when_the_turn_asked_held_answered_or_acted(turn, said, calls, quiet, held, brief):
    turn.update(brief)
    _t, out = _say(said, calls=calls, quiet=quiet, held=held)
    assert out == [], out


def test_a_read_that_did_not_run_is_no_act_to_say_undone(turn, monkeypatch):
    monkeypatch.setattr("widgets.effects.carries", lambda card, action, effect: True)
    assert unserved.calls_not_run([_call("agenda", "list_day")], []) == []


def test_the_turn_hands_the_mouth_the_models_calls_and_whether_any_door_ran():
    """The wiring: the one call of `after_acts` in the post-stream settle passes the model's calls, `quiet` and `held`
    (a mouth that never receives them says nothing undone, and every test above would still be green)."""
    import ast
    import inspect
    from nucleo.flash import post_stream_settle
    tree = ast.parse(inspect.getsource(post_stream_settle))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "after_acts"]
    assert len(calls) == 1, "the turn's acts are said through ONE call of after_acts"
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert {"model_calls", "quiet", "held"} <= set(kw), kw
    assert "_turn_calls" in kw["model_calls"], kw["model_calls"]
