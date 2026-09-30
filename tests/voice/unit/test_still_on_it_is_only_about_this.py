"""Demo pass 2026-09-28, C2: «find me a free 45 minutes tomorrow afternoon to talk with rowan, after my last meeting»
came back MUTE while the monitor search ran, and the mute backstop said «Still on it; I'll let you know as soon as I
have it» — about a request nothing was doing. Our own canned line was the one lying. It now speaks of live work
only when that work is about what he just asked (the conservative V2-176 predicate)."""
from tests import voice_turn_source as _vts
from types import SimpleNamespace as NS

from nucleo.flash import reminder_guards as rg

LANG = NS(filler_still_working="Still on it.", mute_lines=("Sorry, I lost that.",), mute_stuck="stuck")


def _live(monkeypatch, goals):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"request": g} for g in goals])


def test_unrelated_live_work_does_not_make_a_mute_turn_still_on_it(monkeypatch):
    _live(monkeypatch, ["Find three 27-inch 4K monitors under 400 dollars each"])
    said = rg.mute_backstop([], LANG, True, operator_text="find me a free 45 minutes tomorrow afternoon to talk "
                                                          "with rowan, after my last meeting")
    assert said == "Sorry, I lost that."


def test_live_work_about_this_still_says_so(monkeypatch):
    _live(monkeypatch, ["Find three 27-inch 4K monitors under 400 dollars each"])
    assert rg.mute_backstop([], LANG, True, operator_text="how are the 4K monitors going") == "Still on it."


def test_without_his_words_the_old_conduct_stands(monkeypatch):
    _live(monkeypatch, ["anything"])
    assert rg.mute_backstop([], LANG, True) == "Still on it."


def test_both_channels_pass_his_words():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "operator_text=_op_text)" in _vts.read(root / "voice/engine/llm/providers/nucleo.py")
    assert "mute_backstop(sess.window, _lg, _hw, operator_text=text)" in (root / "nucleo/flash/probe.py").read_text("utf-8")
