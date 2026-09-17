"""V2-719 — the Brain Worker's data-op gate decides per CALL, with the ONE consent rule the voice channel uses.

## The measured incident

Session `923f0adc`, 2026-09-17 21:20-21:27. The operator: «Ivan did tell us to send him an invite to Gmail, so
can you please do it?» — and, to this session's agent, «asegúrate de que termine el proceso sin intervención
humana». The worker did everything right: read the Telegram archive, found «can you send me a calendar invite
to: ivan@charms.dev» (18:16), found the 22:00 meeting, composed the one correct call:

    agenda.invite {who: "ivan@charms.dev", meeting: "Ivan", date: "2026-09-17"}

…and `worker_policy.classify_act` parked it on «El worker quiere hacer «invite» en el widget «agenda» (acción
irreversible). ¿Lo autorizas?» — `waiting_on: user`, no TTL, the task at 60 % with its one remaining step
being the send. The gate read `frontend.action_mode`, the manifest flag alone (`invite` declares a
`consent_class` and a `confirm_q`). The voice channel, asked the SAME call through `action_mode_now` (V2-712),
answers FAST: level standard, one named recipient, no standing class rule. Two verdicts for one call, and the
question went to the one person who had asked not to be asked.

The fix is one seam: the worker asks `action_mode_now` with the call's payload, like the voice does. What
stays: an unbounded or ambiguous call still asks (the V2-707 rail), an outward `push_channel` still asks,
`rows.*` is still the generic door, an undeclared action is still denied.
"""
from __future__ import annotations

import pytest

from nucleo.worker_policy import ALLOW, CONFIRM, DENY, classify_act

INVITE = {"widget_id": "agenda", "action": "invite",
          "payload": {"who": "ivan@charms.dev", "meeting": "Ivan", "date": "2026-09-17"}}


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store with the one meeting the real call named — never the operator's calendar. The rule is
    decided per call against the data, so without this meeting the SAME call rightly asks (see below)."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        # the address Ivan gave us himself is on the roster → `calendar.invite_agreed` (V2-718's hook), and
        # that class is `allow` in genesis. The SAME call to a stranger's address is `invite_new_party` → ask.
        {"id": "m1", "title": "Meeting with Ivan Mikushin", "date": "2026-09-17", "startTime": "22:00",
         "attendees": ["Ivan Mikushin", "ivan@charms.dev"]},
        {"id": "m2", "title": "Dentist", "date": "2026-09-18", "startTime": "17:00"},
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


def test_the_real_parked_call_is_allowed(agenda):
    assert classify_act("widget_data", INVITE) == ALLOW


def test_without_the_meeting_the_same_call_asks_which_is_the_rule_working():
    """No fixture: the sandbox agenda holds no Ivan meeting, so the address is a THIRD party to whatever the
    call resolves to — `calendar.invite_new_party`, «ask» in genesis. Data-dependent by design — that is
    what «per call» means, and it is the operator's own criterion (V2-718) reaching the worker unchanged."""
    assert classify_act("widget_data", INVITE) == CONFIRM


def test_a_third_party_still_asks_through_the_worker_too(agenda):
    stranger = {**INVITE, "payload": {**INVITE["payload"], "who": "someone.else@example.com"}}
    assert classify_act("widget_data", stranger) == CONFIRM


def test_the_worker_and_the_voice_give_one_verdict_for_one_call(agenda):
    """The whole point: not «allowed», but «the same answer the voice gives»."""
    from nucleo.flash import frontend
    from widgets import actions as _wa
    voice = frontend.action_mode_now("agenda", "invite", INVITE["payload"])
    assert voice == _wa.FAST
    assert classify_act("widget_data", INVITE) == ALLOW


def test_the_same_action_with_nobody_named_still_asks():
    """Per CALL, not per action: `invite` with no `who` has a missing fact / unbounded target, and the rule
    keeps the friction there — the worker is told to name someone, not waved through."""
    assert classify_act("widget_data", {"widget_id": "agenda", "action": "invite", "payload": {}}) == CONFIRM


def test_the_gate_reads_the_calls_payload_not_the_abstract_flag(agenda):
    """Disarm-shaped: with the payload stripped the verdict must change, which proves the gate is looking at
    the call. (An `action_mode`-only gate answers CONFIRM to both.)"""
    stripped = {k: v for k, v in INVITE.items() if k != "payload"}
    assert classify_act("widget_data", stripped) == CONFIRM
    assert classify_act("widget_data", INVITE) == ALLOW


def test_what_the_old_gate_protected_still_holds():
    assert classify_act("push_channel", {"channel": "telegram"}) == CONFIRM     # outward, cannot be undone
    assert classify_act("widget_data", {"widget_id": "agenda", "action": "rows.delete"}) == ALLOW  # V2-711 T0.2
    assert classify_act("widget_data", {"widget_id": "agenda", "action": "no_such_action"}) == DENY
    assert classify_act("widget_data", {"widget_id": "nope", "action": "invite", "payload": {}}) == DENY


def test_the_worker_gate_names_the_per_call_seam_and_not_the_abstract_one():
    src = open("nucleo/worker_policy.py", encoding="utf-8").read()
    body = src[src.index('if a == "widget_data":'):src.index('if a == "spawn":')]
    assert "action_mode_now(" in body
    assert "import action_mode\n" not in body and "action_mode(" not in body.replace("action_mode_now(", "")
