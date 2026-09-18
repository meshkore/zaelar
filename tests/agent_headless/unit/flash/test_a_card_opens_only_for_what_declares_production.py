"""V2-721 — a card's open/closed flag moves only for an action the widget DECLARES as production.

## The measured incident

Session `c553a1e0`, 2026-09-17, with a guest watching. Music was playing; the operator paused it («let's
pause this thing»), asked for his agenda, closed everything — and four minutes later, in the middle of a
sentence about his headphones («I think the sound is mixing with the headphones»), the music card came back
on screen three times and the player woke up. His reading of it afterwards:

> «ha habido como un baile de abrir y cerrar widgets sin mi permiso […] los widgets no dejan de ser un
> catálogo y deben tener un flag de si están abiertos o cerrados. A menos que haya una acción concreta que
> interprete que uno de esos widgets tiene que cambiar el flag de visibilidad […] no deberíamos en absoluto
> tener ningún problema con eso.»

The flag exists and is authoritative (`/api/canvas/state` → `memory.state()["open_widgets"]`). What nobody
owned was who may MOVE it. The voice lane opened the card on every successful music action, because the
connector's result says `surface: "widget"` — and `pause`, `volume_up`, `seek` and `queue` all say it too.
That field is a fact about where the AUDIO is, not an instruction about the screen.

## What this pins

  1. `canvas_visibility.mount_needed` — only a DECLARED producer opens a card, and never one already open.
  2. The arbiter agrees through the SAME declaration: a mount is not a drag. Of the six `show-drag`
     verdicts over the music card in twelve real sessions, five were a `pause`/`stop`/`volume_up` putting
     the card back on his screen and one was an honest mount of a play he had just asked for — so arming
     the arbiter as it stood would have answered that one with silence.

The same complaint is on record a day earlier, session `928c8761` at 772 s, in his own words while the
card jumped up on a `stop`: «I did pause it manually, and you did start it without my request.»
  3. The call site passes the action, so the two can agree at all.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nucleo import canvas_arbiter as arb
from nucleo.flash import canvas_license as lic, canvas_visibility as cv

ENGINE = Path(__file__).resolve().parents[4]

#: What the music connector hands back for every action: where the sound comes from, nothing more.
WIDGET_SURFACE = {"surface": "widget", "widget": "musica"}
#: `musica` declares `runtime.produce = [play, resume, next, previous, play_playlist, ended]`.
PRODUCERS = ("play", "resume", "next", "previous", "play_playlist", "ended")
CONTROLS = ("pause", "volume_up", "volume_down", "set_volume", "seek", "queue", "favorite_current")


@pytest.fixture(autouse=True)
def _fresh_reopen_state():
    lic._RECENT_CLOSES.clear()
    yield
    lic._RECENT_CLOSES.clear()


# ── 1 · the flag moves only for what the widget declares ─────────────────────────────────────────────────

@pytest.mark.parametrize("action", CONTROLS)
def test_a_control_never_opens_the_card(action):
    """The three that actually happened to him: pause re-opened the card he had closed, and volume_up put
    it back in front of him while he was talking about something else."""
    assert cv.mount_needed(WIDGET_SURFACE, action, known=[]) is False


@pytest.mark.parametrize("action", PRODUCERS)
def test_a_declared_producer_opens_it_because_the_sound_lives_there(action):
    """Not a courtesy: the audio is a hidden iframe INSIDE the card, so a play off screen is silence."""
    assert cv.mount_needed(WIDGET_SURFACE, action, known=[]) is True


@pytest.mark.parametrize("action", PRODUCERS + CONTROLS)
def test_an_open_card_is_never_shown_again(action):
    """The other half of the dance: a `show` on an open card raises and refocuses it, jumping in front of
    whatever he was reading. If it is open there is nothing to open."""
    assert cv.mount_needed(WIDGET_SURFACE, action, known=["musica"]) is False


def test_an_instance_id_counts_as_the_same_card():
    assert cv.mount_needed(WIDGET_SURFACE, "play", known=["musica::t2"]) is False


def test_output_that_does_not_live_in_the_card_never_touches_the_canvas():
    """Spotify plays on a device: there is no surface to mount, so the screen is not part of the act."""
    assert cv.mount_needed({"surface": "device", "widget": "musica"}, "play", known=[]) is False
    assert cv.mount_needed({}, "play", known=[]) is False
    assert cv.mount_needed(None, "play", known=[]) is False


def test_an_undeclared_action_leaves_the_card_where_the_operator_put_it():
    """Fails toward NOT moving the flag — the direction that cannot surprise him."""
    assert cv.mount_needed(WIDGET_SURFACE, "", known=[]) is False
    assert cv.mount_needed(WIDGET_SURFACE, "nonexistent_action", known=[]) is False
    assert cv.mount_needed({"surface": "widget", "widget": "no_such_widget"}, "play", known=[]) is False


def test_the_open_set_is_read_from_the_canvas_own_report(monkeypatch):
    """`open_widgets` is written by the frontend, which is authoritative for the canvas, and normalized to
    base ids — so this reads the flag the operator himself moves when he clicks the close button."""
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["musica::t1", "Agenda"]})
    assert cv.open_ids() == frozenset({"musica", "agenda"})
    assert cv.is_open("musica") and cv.is_open("agenda") and not cv.is_open("youtube")
    assert cv.mount_needed(WIDGET_SURFACE, "play") is False      # already open → no show

    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": []})
    assert cv.mount_needed(WIDGET_SURFACE, "play") is True


def test_an_unreadable_state_costs_a_show_and_never_a_lost_playback(monkeypatch):
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert cv.open_ids() == frozenset()
    assert cv.mount_needed(WIDGET_SURFACE, "play") is True


# ── 2 · the arbiter judges by the SAME declaration ───────────────────────────────────────────────────────

def test_the_arbiter_calls_an_honest_mount_a_mount_and_not_a_drag():
    """The turn that plays the music rarely names the widget («I've just said Bruce»), so the show that
    mounts the player looked like a drag. Four of the twelve sessions' fifteen `show-drag` verdicts were
    this, and arming the arbiter without this rule would have muted the playback."""
    v = arb.decide("show", "musica", "flash", action="play", text="I've just said Bruce.", turn_credit=True)
    assert v.allow is True and v.rule == "producer-mount"


def test_the_arbiter_still_vetoes_the_shows_that_were_the_dance():
    """The same door, same turn text, the actions that are not production: these are the three that put
    the card back on his screen while he talked about headphones."""
    said = "I think the sound is mixing with the headphones or something because I don't listen"
    for action in ("pause", "volume_up", ""):
        v = arb.decide("show", "musica", "flash", action=action, text=said, turn_credit=True)
        assert v.allow is False and v.rule == "show-drag", action


def test_a_mount_does_not_override_an_order_to_close():
    """Precedence is untouched (V2-567): a show against a close order is the model contradicting him,
    whatever the action claims to be."""
    v = arb.decide("show", "musica", "flash", action="play", text="cierra la música", turn_credit=True)
    assert v.allow is False and v.rule == "show-against-close-order"


def test_a_widget_that_declares_no_production_gets_no_mount():
    """The rule rides the manifest, so it cannot be spent by naming any action `play`."""
    said = "I think the sound is mixing with the headphones"
    v = arb.decide("show", "agenda", "flash", action="add_meeting", text=said, turn_credit=True)
    assert v.allow is False and v.rule == "show-drag"


def test_an_ambient_turn_still_opens_nothing():
    """Level 2 comes first: with no credit for the turn, nothing the model does reaches the canvas."""
    v = arb.decide("show", "musica", "flash", action="play", text="…", turn_credit=False)
    assert v.allow is False and v.rule == "ambient-turn"


def test_the_operators_own_hands_are_never_judged_by_this_rule():
    v = arb.decide("show", "musica", "user", action="", text="", turn_credit=False)
    assert v.allow is True and v.rule == "operator-hands"


# ── 3 · the wiring, so the two can agree at all ──────────────────────────────────────────────────────────

def test_the_voice_lane_goes_through_the_door_and_names_its_reason():
    """V2-723 moved the gate INTO the door: the lane no longer emits a show at all, it asks to present and
    says why. The claim is then checked against the widget's declaration inside `present`."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    m = re.search(r'_cvis\.present\(str\(_extra\.get\("widget"\).*?reason="producer-mount".*?'
                  r'action=mq\.get\("action"\)', src, re.S)
    assert m, "the music lane must present through the door, declaring `producer-mount` and its action"
    assert 'emit("widget", "show"' not in src, \
        "no anonymous show may be left in the voice provider — everything goes through the door"


def test_the_shadow_tap_carries_the_action_of_a_show():
    src = (ENGINE / "nucleo/canvas_arbiter.py").read_text(encoding="utf-8")
    body = src[src.index("if label in _SHOW_LABELS:"):]
    assert 'ex.get("action")' in body.split("elif", 1)[0], \
        "a show's action must reach `decide`, or every mount is judged as an anonymous show"


def test_both_sides_read_one_declaration_and_not_two_lists():
    """No verb table anywhere: `producers.starts_production` is the single source, and a widget that
    changes its manifest changes both answers at once."""
    from widgets import producers
    for action in PRODUCERS:
        assert producers.starts_production("musica", action) is True, action
    for action in CONTROLS:
        assert producers.starts_production("musica", action) is False, action
    arb_src = (ENGINE / "nucleo/canvas_arbiter.py").read_text(encoding="utf-8")
    vis_src = (ENGINE / "nucleo/flash/canvas_visibility.py").read_text(encoding="utf-8")
    assert "producers.starts_production" in arb_src and "producers.starts_production" in vis_src
