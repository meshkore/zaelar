"""«Stop the video and close youtube»: the op inside the card runs, and the card he NAMED closes after it.

Demo pass 2026-09-28 (V7, two passes running): the model called `youtube:close` — which empties the player, as
its manifest says — and the card stayed open, hiding every card after it. The canvas verdict cannot tell the two
orders apart (measured: Jev reads «close the video» 0.99 and «close youtube» 0.99 both as canvas=close), and
«close the video» must keep the card (V2-753). What separates them is whether his words call the card by what it
is CALLED — its catalogue name in any bundle — or only by what it holds."""
from tests import voice_turn_source as _vts
import pathlib

import pytest

from nucleo.flash import direct_action as da

ENGINE = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def close_verdict(monkeypatch):
    from nucleo.flash import turn_brief as tb
    monkeypatch.setattr(tb, "read", lambda brief, key, default="", min_confidence=0.0:
                        ("close", {}) if key == tb.CANVAS_KEY else (default, {}))
    monkeypatch.setattr(da, "_open_now", lambda: ["youtube", "agenda"])


@pytest.mark.parametrize("said", ["ok stop the video and close youtube", "para el vídeo y cierra YouTube"])
def test_the_card_called_by_its_name_closes_after_the_op(close_verdict, said):
    assert da.closes_the_named_card({}, said, [("youtube", "close")]) == "youtube"


@pytest.mark.parametrize("said", ["close the video", "quita el vídeo"])
def test_the_video_named_by_what_the_card_holds_keeps_the_card(close_verdict, said):
    assert da.closes_the_named_card({}, said, [("youtube", "close")]) == ""


def test_the_name_is_read_in_every_catalogue_language():
    names = {n.casefold() for n in da.catalogue_names("agenda")}
    assert {"agenda", "calendar"} <= names
    assert "video" not in {n.casefold() for n in da.catalogue_names("youtube")}, "an alias is not the card's name"


def test_a_card_that_is_not_open_is_not_closed(close_verdict):
    assert da.closes_the_named_card({}, "stop the map and close the map", [("map", "clear")]) == ""


def test_both_channels_wire_it():
    voice = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    probe = _vts.read(ENGINE / "nucleo/flash/probe.py")
    assert "_direct_action.closes_the_named_card(_brief, _op_text, data_done.get(\"ops\"))" in voice
    assert 'data_done.setdefault("ops", []).append((wid, action_name))' in voice
    assert "closes_the_named_card(_tbrief, operator_text, _ops)" in probe


def test_the_in_card_guard_lets_the_named_close_through():
    """full18 V7: the close was emitted and the «order is an action INSIDE the card» guard dropped it."""
    voice = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    assert '_tag_emit("close", {"id": _cn, "named": True})' in voice
    i = voice.index('close ignorado — la orden es una acción DENTRO de la tarjeta')
    guard = voice[voice.rindex("if (action", 0, i):i]
    assert 'not (extra or {}).get("named")' in guard


def test_tidying_the_screen_is_a_canvas_gesture_the_verdict_can_complete(monkeypatch):
    """full21 C5b: «tidy up the screen a bit» → «screen's sorted» with no call; the canvas verdict could only say
    `neither`, because laying the cards out was not one of its gestures."""
    from nucleo.flash import show_target as st
    from nucleo.flash import turn_brief as tb
    assert "arrange" in st.CANVAS_VERBS
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=0.0:
                        ("arrange", {"used": True}) if k == tb.CANVAS_KEY else (d, None))
    ev = []
    assert da.complete_canvas({"x": 1}, tag_emit=lambda a, x: ev.append(("tag", a)),
                              emit=lambda *a, **k: ev.append(a[:2]), operator_text="tidy up the screen") == "arrange"
    assert ("widget", "arrange") in ev and not any(e[0] == "tag" for e in ev)
    probe = _vts.read(ENGINE / "nucleo/flash/probe.py")
    # the text channel's mirror lives in `card_close.complete_canvas_mirror` since V2-781 (it also runs before the repair)
    assert "_card_close.complete_canvas_mirror(" in probe
    assert 'if verb == "arrange":' in (ENGINE / "nucleo/flash/card_close.py").read_text(encoding="utf-8")
