"""A turn that ACTED without a word still answered its order (demo run, 2026-09-26).

«Play video number 2» played it and said nothing, so the window held «Play video number 2» and «Make it
fullscreen» back to back — the shape that means «that one went unanswered». The model re-emitted
`youtube:play_result {item: 2}`, the context-bleed guard dropped it, and the reply was «Sorry, I lost that»
with no fullscreen. Both channels now close a silent action with the short ack.
"""
import pathlib
import re

from nucleo.flash import dialog

ROOT = pathlib.Path(__file__).resolve().parents[4]


def test_a_silent_action_leaves_its_ack_after_the_order():
    win = [{"role": "user", "content": "Play video number 2."}]
    dialog.record_silent_action(win, "Done.")
    assert win[-1] == {"role": "assistant", "content": "Done."}


def test_it_never_invents_an_answer_where_nothing_was_asked_or_one_was_given():
    win = [{"role": "user", "content": "Play it."}, {"role": "assistant", "content": "Playing."}]
    dialog.record_silent_action(win, "Done.")
    assert len(win) == 2, "an order that was already answered gets no second answer"
    empty: list = []
    dialog.record_silent_action(empty, "Done.")
    assert empty == []
    one = [{"role": "user", "content": "x"}]
    dialog.record_silent_action(one, "  ")
    assert one == [{"role": "user", "content": "x"}], "no ack text, no line"


def test_the_voice_channel_records_it_when_a_tool_handled_the_turn():
    src = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert re.search(r"brain\._window\.append\(\{\"role\": \"assistant\", \"content\": _dialog\.sanitize_reply"
                     r"\(spoken_text\)\}\)\n\s+elif _tool_handled:\n\s+_dialog\.record_silent_action\("
                     r"brain\._window, _say\(\)\.data_ack\)", src), "voice: a silent tool turn must close its order"


def test_the_text_channel_records_it_too():
    src = (ROOT / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert re.search(r"sess\.window\.append\(\{\"role\": \"assistant\", \"content\": spoken\}\)\n\s+elif tags or "
                     r"tool_calls:\n.*\n\s+dialog\.record_silent_action\(sess\.window, ", src), "text channel parity"


def test_the_action_map_lane_records_it_too():
    """«Close the music player» went through the action map (no model, silent); the next turn answered it
    again — «closing the player now» — and reopened the player."""
    src = (ROOT / "voice/engine/llm/providers/fast_lane.py").read_text(encoding="utf-8")
    i = src.index("_dialog0.push_user(brain._window, text)")
    assert "_dialog0.record_silent_action(brain._window," in src[i:i + 600]
