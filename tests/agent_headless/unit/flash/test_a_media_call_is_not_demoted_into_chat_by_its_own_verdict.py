"""A `show_images` the model called is the act, not a canvas gesture a repair may demote (2026-10-11).

`show-real-photo-of-a-new-car__us`, turn 2: «I don't see any photo — send the actual pic.» The model called
`show_images {query: "Ferrari Amalfi"}`, the text channel named the turn `canvas:show:imagenes`, the verdict read
`screen_action = imagenes:show` (0.59), and the V2-770 repair (a show of an open card whose verdict names an action
INSIDE it is not the act) demoted the action to `chat`. The parked search never ran and the mute backstop said
«Sorry, I lost that. Could you say it again?».

Disarm (done while writing this): with `carries_media_request` returning False for every call, the second test fails
and the source assertion fails — the predicate is what stands between the search and the demotion.
"""
from __future__ import annotations

from pathlib import Path

from nucleo.flash import media_show as MS

ENGINE = Path(__file__).resolve().parents[4]


def test_the_show_a_media_tool_fills_carries_the_request():
    assert MS.carries_media_request("canvas:show:imagenes", ["show_images"])
    assert MS.carries_media_request("canvas:show:youtube", ["play_video"])
    assert MS.carries_media_request("canvas:show:imagenes::t1", ["recall", "show_images"])


def test_a_bare_show_or_another_card_carries_nothing():
    """`show_widget(agenda)` over an open agenda is exactly the case V2-770 repairs: it stays demotable."""
    assert not MS.carries_media_request("canvas:show:agenda", ["show_widget"])
    assert not MS.carries_media_request("canvas:show:imagenes", ["show_widget"])
    assert not MS.carries_media_request("canvas:show:youtube", ["show_images"])
    assert not MS.carries_media_request("chat", ["show_images"])
    assert not MS.carries_media_request("", [])


def test_the_text_channel_asks_the_predicate_before_demoting_a_show():
    """The V2-770 demotion in `probe_mirrors` is gated by the predicate — the wire, not just the module."""
    src = (ENGINE / "nucleo/flash/probe_mirrors.py").read_text(encoding="utf-8")
    i = src.index("order_is_inside(_tbrief, action.split")
    window = src[max(0, i - 400):i]
    assert "carries_media_request(action, names)" in window, "the demotion no longer asks whether the show IS the call"
