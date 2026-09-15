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


# ── the meeting VOCABULARY must catch a plain proposal (V2-705) ──────────────────────────────────────────
# Measured 2026-09-15: «Could we meet this Friday… Google Meet link» classified as GENERIC, so the errand
# never opened — «meeting»/«reunión» were match words but the bare verb «meet» and «Google Meet» were not.

import pytest


@pytest.mark.parametrize("text", [
    "Hi! Could we meet this Friday, September 18th, at 10am? I will set up a Google Meet link for us.",
    "Hi! I'd like to propose a meeting tomorrow at 8am. I'll set up a Google Meet link.",
    "Let's set up a video call on Friday",
    "¿Quedamos el viernes para vernos?",
])
def test_a_plain_meeting_proposal_classifies_as_meeting(text):
    from nucleo.errands.playbooks import kind_for
    assert kind_for(text) == "meeting", text


@pytest.mark.parametrize("text", [
    "Nice to meet you!",
    "Running late, see you at 5",
    "Thanks, got it.",
])
def test_a_friendly_line_is_not_a_meeting(text):
    """«meet» alone is too broad — «nice to meet you» is not a proposal. The match words stay specific:
    «meet link», «meet up», «video call», never the bare verb — and never a COMPANY either: «google meet»
    was one of them for an hour, until `test_nothing_in_a_playbook_names_a_person_or_a_company` said so.
    «meet link» catches «Google Meet link» without the playbook knowing who makes it."""
    from nucleo.errands.playbooks import kind_for
    assert kind_for(text) != "meeting", text


# ── …but an errand's OWN voice opens nothing (V2-705) ───────────────────────────────────────────────────
# Measured 2026-09-15 20:46, on the run that finally closed the Thursday meeting end to end: the errand
# booked the meeting, minted the Meet link and sent «Great! So we're set for Thursday, September 17th, at
# 5:00pm. Here's the Google Meet link…» — and the autonomy net above read that confirmation as a fresh
# proposal, opened a SECOND errand, and `claim()` took the conversation off the first one. It closed
# harmlessly only because the meeting it was about already existed; one beat earlier it would have taken
# the thread from a LIVE errand and answered the same person against a different objective.

def test_a_message_an_errand_SENT_never_opens_another_one(monkeypatch):
    import nucleo.errands.watch as w
    real = {"e7457588--b60xTk": {"id": "e7457588--b60xTk", "state": "contacting"}}
    monkeypatch.setattr("nucleo.errands.get", lambda eid: real.get(eid))
    drained = {"send": [
        # the errand's own confirmation — `wake._send` stamps «<errand id>:<epoch>» as the queue ref
        {"ref": "e7457588--b60xTk:1789497987",
         "text": "Great! So we're set for Thursday, September 17th, at 5pm. Here's the Google Meet link."},
        # …and an order the operator gave, whose ref names no errand
        {"ref": "s7453164-dnIWZ5IV",
         "text": "Hi! Could we meet this Thursday at 5pm? I'll set up a Google Meet link."},
    ], "failed": []}
    monkeypatch.setattr(w, "_drain", lambda which: drained.get(which, []))
    w._pending_births.clear()
    w._note_births(1000.0)
    born = set(w._pending_births)
    w._pending_births.clear()
    assert born == {"s7453164-dnIWZ5IV"}, born


def test_the_sender_is_read_from_the_STORE_not_from_the_shape_of_the_ref(monkeypatch):
    """A ref that merely LOOKS like an errand id opens its errand normally — the gate asks the store."""
    import nucleo.errands.watch as w
    monkeypatch.setattr("nucleo.errands.get", lambda eid: None)
    assert w._own_errand("e7457588--b60xTk:1789497987") == ""
    monkeypatch.setattr("nucleo.errands.get", lambda eid: {"id": eid})
    assert w._own_errand("e7457588--b60xTk:1789497987") == "e7457588--b60xTk"
    assert w._own_errand("") == "" and w._own_errand(None) == ""


def test_an_explicit_objective_does_not_buy_an_errand_a_second_one(monkeypatch):
    """Not even a LABELLED send re-opens: an errand's own voice is never a new order from the operator."""
    import nucleo.errands.watch as w
    monkeypatch.setattr("nucleo.errands.get", lambda eid: {"id": eid})
    monkeypatch.setattr(w, "_drain", lambda which: (
        [{"ref": "e1:9", "objective": "organise another meeting", "text": "x"}] if which == "send" else []))
    w._pending_births.clear()
    w._note_births(1000.0)
    born = set(w._pending_births)
    w._pending_births.clear()
    assert born == set(), born
