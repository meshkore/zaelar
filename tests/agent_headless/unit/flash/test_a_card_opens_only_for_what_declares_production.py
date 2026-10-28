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

from tests import voice_turn_source as _vts

import re
from pathlib import Path

import pytest

from nucleo.acts import canvas_arbiter as arb
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
    src = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    m = re.search(r'_cvis\.present\(str\(_extra\.get\("widget"\).*?reason="producer-mount".*?'
                  r'action=mq\.get\("action"\)', src, re.S)
    assert m, "the music lane must present through the door, declaring `producer-mount` and its action"
    assert 'emit("widget", "show"' not in src, \
        "no anonymous show may be left in the voice provider — everything goes through the door"


def test_both_sides_read_one_declaration_and_not_two_lists():
    """No verb table anywhere: `producers.starts_production` is the single source, and a widget that
    changes its manifest changes both answers at once."""
    from widgets import producers
    for action in PRODUCERS:
        assert producers.starts_production("musica", action) is True, action
    for action in CONTROLS:
        assert producers.starts_production("musica", action) is False, action
