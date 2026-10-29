"""What the agent says about a video's SOUND comes from the card's state, never from its intention (V2-831 V2).

Demo smoke 2, V2: «play the second one» → the model called `play_result` only and said «Here it is, the fifth flight
test — unmuting so you can hear it» while the player stayed MUTED (autoplay policy; the op's own result said
`muted`). The card's usage told the model «usa 'unmute' para que se oiga», and the model narrated the act instead of
calling it. The widget's usage — the one place this house keeps rails — now makes a sound claim follow the state the
card returns (`muted`, `audio_blocked`) and the call actually made.

Disarm: put the old usage sentence back → red.
"""
from __future__ import annotations

import json
import pathlib

_MANIFEST = pathlib.Path(__file__).resolve().parents[4] / "widgets" / "youtube" / "manifest.json"


def test_a_sound_claim_follows_the_cards_returned_state():
    usage = json.loads(_MANIFEST.read_text(encoding="utf-8"))["usage"]
    assert "del SONIDO di solo lo que devuelve la tarjeta" in usage
    assert "`muted`" in usage and "`audio_blocked`" in usage
    assert "LLAMA a 'unmute'" in usage, "the usage no longer says that hearing it takes a CALL"
    # kept short: every char of a card's usage rides every turn it is open (`test_the_turn_prompt_has_a_ceiling`)


def test_the_card_returns_the_state_the_claim_is_read_from():
    """The claim has something to follow: every player op returns `muted` and `audio_blocked` (`helpers._bump`)."""
    src = (_MANIFEST.parent / "helpers.py").read_text(encoding="utf-8")
    assert '"muted": db.get("muted")' in src and '"audio_blocked": bool(db.get("audio_blocked"))' in src
