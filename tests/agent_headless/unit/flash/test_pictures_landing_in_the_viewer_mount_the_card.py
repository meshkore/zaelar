"""Pictures landing in the viewer are a MOUNT, not a drag (2026-10-11, `show-real-photo-of-a-new-car__us`).

The round filed three `⛔ show-drag` verdicts on `imagenes` in a plain show/select flow. Who emitted them: the
picture search (`image_turn.execute`) emitted a bare `show` after loading the viewer, and the generic data-op path
(`widget_data_turn`) emitted a bare `show` after `select` on a card already open. Neither said WHICH action put the
card up, and the arbiter can only call a mount a mount when the emit names the action the card declares.

Three mechanisms, each one a measured half of the fix:
  1. `effects.of("imagenes", "show")` carries `present.mount`, derived from the action's own `done_when`
     (`field: items, expect: present`) — the card goes from empty to holding what he asked to SEE.
  2. the arbiter answers `content-mount` for a `show` that carries that effect; a bare show and a lens (`select`)
     still earn nothing.
  3. the two emitters name the action: the search goes through the one door (`canvas_visibility.present`), and the
     data-op path does not raise a card already in front of him.

Disarm: with `_fills_the_card` returning False the first two tests go red; with the `action` dropped from the
`widget_data_turn` emit the source test goes red.
"""
from __future__ import annotations

from pathlib import Path

from nucleo.acts import canvas_arbiter as arb
from nucleo.flash import canvas_visibility as cv
from widgets import effects as fx

ENGINE = Path(__file__).resolve().parents[4]
SAID = "I don't see any photo — you just said here they are. Send the actual pic."


def test_the_viewer_declares_that_its_show_fills_it():
    assert fx.PRESENT_MOUNT in fx.of("imagenes", "show")
    assert fx.PRESENT_MOUNT not in fx.of("imagenes", "select"), "a lens over an open card mounts nothing"
    assert not fx._fills_the_card("youtube", {"widget": "youtube", "field": "videoId", "expect": "changed"}), \
        "`changed` is a different video, not content arriving (the player's mount rides its production instead)"
    assert not arb._lands_content("youtube", "load"), "production is judged by its own leaf, never twice"
    assert fx._fills_the_card("x", {"all": [{"widget": "x", "field": "a", "expect": "present"}]})
    assert not fx._fills_the_card("x", {"widget": "y", "field": "a", "expect": "present"})


def test_the_arbiter_calls_the_filling_show_a_mount_and_the_bare_one_a_drag():
    v = arb.decide("show", "imagenes", "flash", action="show", text=SAID, turn_credit=True)
    assert v.allow is True and v.rule == "content-mount"
    for action in ("", "select", "next"):
        v = arb.decide("show", "imagenes", "flash", action=action, text=SAID, turn_credit=True)
        assert v.allow is False and v.rule == "show-drag", action
    # production is still production, judged by its own leaf
    said = "I think the sound is mixing with the headphones"      # licenses no media by itself (V2-721's case)
    v = arb.decide("show", "youtube", "flash", action="next", text=said, turn_credit=True)
    assert v.allow is True and v.rule == "producer-mount"


def test_the_door_lets_the_filling_show_through_and_names_its_action(monkeypatch):
    got = []
    assert cv.present("imagenes", reason="producer-mount", action="show", src="flash", known=[],
                      emit=lambda k, l, extra: got.append((k, l, extra))) is True
    assert got and got[-1][:2] == ("widget", "show") and got[-1][2]["action"] == "show"
    got.clear()
    assert cv.present("imagenes", reason="producer-mount", action="show", src="flash", known=["imagenes"],
                      emit=lambda k, l, extra: got.append((k, l, extra))) is False, "an open viewer is not raised again"


def test_the_picture_search_mounts_through_the_one_door():
    img = (ENGINE / "nucleo/flash/image_turn.py").read_text(encoding="utf-8")
    assert 'emit("widget", "show"' not in img, "the picture search emits through the one door now"
    assert 'present("imagenes", reason="producer-mount", action="show"' in img
