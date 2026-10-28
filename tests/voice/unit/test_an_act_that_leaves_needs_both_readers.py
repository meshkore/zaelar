"""Demo pass 2026-09-28, full12 E3 — a REAL email left for a third party.

«draft a short reply saying i'll send the meet link right after our call»: the verdict read `mensajeria:draft` at
1.00, the model called `reply` (which SENDS), V2-712 ran it without a question (clear order, resolved target) and
«Hi Sam, thanks for the note. I'll send the Meet link right after our call.» went to x@example.com. V2-754 lets a
valid model call beat a disagreeing verdict because a wrong verdict costs a reversible view; for an act that leaves
(consent level ≥ sensitive) the costs are reversed. When the two readers disagree, the verdict's action runs with the
model's content, or he is asked; agreement, or no verdict, changes nothing (C5's Telegram to Rowan still goes)."""
from tests import voice_turn_source as _vts
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_a_reply_is_an_act_that_leaves_and_a_draft_is_not():
    from nucleo.flash import frontend as f
    assert f.at_least_sensitive("mensajeria", "reply")
    assert f.at_least_sensitive("mensajeria", "send_draft")
    assert not f.at_least_sensitive("mensajeria", "draft")
