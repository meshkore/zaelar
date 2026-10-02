from tests import voice_turn_source as _vts
"""What the agent said on its own enters the brain's window at its next prompt (node 3.110).

Manual session 7850de3f (2026-09-30): the INIT list finished in three minutes and said «I've finished your list»
out loud through `proactive.notify`, which never wrote the brain's own window. An hour later the window still
ended in «I'm on them and I'll let you know when I'm done», and the model said «it's all still running in the
background», then «I'm kicking it off now properly» with nothing behind it.
"""
import asyncio

import pytest

from nucleo.flash import dialog
from voice import proactive


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    dialog._SPOKEN.clear()
    yield
    dialog._SPOKEN.clear()


def test_a_spoken_delivery_is_our_next_turn_in_the_window(monkeypatch):
    said = []
    monkeypatch.setattr(proactive, "_speaker", lambda text: said.append(text))
    monkeypatch.setattr(proactive, "_wait_turn", lambda ticket, wait: True)

    async def _quiet(left):
        return True
    monkeypatch.setattr(proactive, "_wait_for_quiet", _quiet)
    assert asyncio.run(proactive.notify("lista", "I've finished your list: 26 of 26 done.", opens_window=False))
    window = [{"role": "user", "content": "DEMO INITIALIZATION …"},
              {"role": "assistant", "content": "Got it — I'm on them and I'll let you know when I'm done."}]
    dialog.drain_spoken(window)
    assert window[-1] == {"role": "assistant", "content": "I've finished your list: 26 of 26 done."}
    dialog.drain_spoken(window)
    assert len(window) == 3, "drained once, never twice"


def test_nothing_said_adds_nothing():
    window = []
    dialog.drain_spoken(window)
    assert window == []


def test_the_prompt_is_built_after_the_drain():
    import inspect

    from voice.engine.llm.providers import nucleo
    src = _vts.turn_source()
    assert src.index("_dialog.drain_spoken(brain._window)") < src.index(
        "messages += _dialog.prune_window(brain._window)")


# ── V2-778 F2-21: both channels hear it (the operator's decision, 2026-10-02) ──────────────────────────────

def test_the_voice_and_a_chat_session_each_get_the_line_once():
    """What was said out loud belongs to the conversation on BOTH channels: draining it into one must not take
    it from the other (before, the first consumer emptied the list)."""
    chat = []
    dialog.drain_spoken(chat, channel="text:a")          # the chat session exists before the line is said
    dialog.note_spoken("I've finished your list: 26 of 26 done.")
    voice = []
    dialog.drain_spoken(voice)
    dialog.drain_spoken(chat, channel="text:a")
    assert voice[-1]["content"] == chat[-1]["content"] == "I've finished your list: 26 of 26 done."
    dialog.drain_spoken(voice)
    dialog.drain_spoken(chat, channel="text:a")
    assert len(voice) == 1 and len(chat) == 1, "each channel once, never twice"


def test_a_chat_session_opened_after_the_line_does_not_inherit_it():
    dialog.note_spoken("Your errand is done.")
    late = []
    dialog.drain_spoken(late, channel="text:late")
    assert late == [], "a line said before this conversation existed is not part of it"


def test_the_text_channel_drains_before_it_builds_the_prompt():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "nucleo" / "flash" / "probe_before.py").read_text("utf-8")
    assert "dialog.drain_spoken(sess.window" in src and src.index("dialog.drain_spoken(sess.window") < src.index(
        "messages += dialog.prune_window(sess.window)")
