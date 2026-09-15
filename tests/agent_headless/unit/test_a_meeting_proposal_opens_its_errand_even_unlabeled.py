"""V2-705 · A meeting proposal opens its follow-through errand even when the model forgot to label it.

Measured 2026-09-15 (the manual autonomy test): Zaelar sent «Hi! I'd like to propose a meeting tomorrow at
8am. I'll set up a Google Meet link.» to the contact — the routing was right, the message really left — but
the model dropped the `objective` on that turn, so `watch._note_births` refused the birth, no errand
existed, and the operator's «Yes, I agree» on Telegram woke nothing. The meeting never booked itself, and
the whole workflow's autonomy hung on the model remembering one optional field.

`watch._gestion_objective` closes it: an outbound message that itself READS as a meeting proposal seeds the
objective from its own text, so the errand is born and can wake on the reply. Restricted to `meeting`, so an
ordinary one-off message opens nothing.
"""
from __future__ import annotations

import pytest

from nucleo.errands import watch


def test_an_explicit_objective_is_used_verbatim():
    assert watch._gestion_objective({"ref": "r", "objective": "Propose X and book it", "text": "hi"}) \
        == "Propose X and book it"


def test_a_meeting_proposal_with_no_objective_seeds_one_from_its_text():
    ev = {"ref": "r", "objective": "",
          "text": "Hi! I'd like to propose a meeting tomorrow at 8am. I'll set up a Google Meet link."}
    seeded = watch._gestion_objective(ev)
    assert seeded == ev["text"]
    from nucleo.errands.playbooks import kind_for
    assert kind_for(seeded) == "meeting", "the seeded objective must classify as a meeting errand"


@pytest.mark.parametrize("text", [
    "Running late, see you at 5!",
    "Thanks, got it.",
    "Here is the document you asked for.",
])
def test_an_ordinary_message_opens_nothing(text):
    assert watch._gestion_objective({"ref": "r", "objective": "", "text": text}) == ""


def test_an_empty_send_opens_nothing():
    assert watch._gestion_objective({"ref": "r", "objective": "", "text": ""}) == ""
    assert watch._gestion_objective({}) == ""


def test_the_births_gate_uses_the_seam(monkeypatch):
    """Structural: `_note_births` births through `_gestion_objective`, so a labelled AND an unlabelled
    proposal both reach `_pending_births`, and a one-off reaches neither."""
    import nucleo.errands.watch as w
    drained = {"send": [
        {"ref": "labelled", "objective": "arrange the call", "text": "x"},
        {"ref": "proposal", "objective": "", "text": "Let's set up a meeting Friday; I'll send a Meet link."},
        {"ref": "oneoff", "objective": "", "text": "on my way"},
    ], "failed": []}
    monkeypatch.setattr(w, "_drain", lambda which: drained.get(which, []))
    w._pending_births.clear()
    w._note_births(1000.0)
    born = set(w._pending_births)
    w._pending_births.clear()
    assert "labelled" in born and "proposal" in born and "oneoff" not in born, born
