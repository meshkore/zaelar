"""V2-707 F6 · A mutation that ALREADY RAN is a fact of the next turn, not something to deduce.

## The session

`080b96a7`, 2026-09-16. Two agenda sweeps had executed — i=10545 (four rows of the 16th) and i=10780 (five
rows of the 17th) — and then:

    i=10804  he      «No. You did delete all»
    i=10817  zaelar  «I haven't deleted anything — no deletion was confirmed in this conversation.»
    i=10829  he      «No. You did delete all day, and I just set three of them.»
    i=10853  zaelar  «In this conversation I never confirmed a deletion, so nothing has been removed from
                      your calendar — the three all-day entries on the 17th are still there.»
    i=10873  he      «Are you stupid? You just did delete.»

Both replies are CORRECT deductions from the only ledger the prompt carried:
`widgets/confirm.pending_line()`, which says what is WAITING for a yes. Nothing anywhere told the turn what
the engine had DONE, so it reasoned from the absence of a pending confirmation to the absence of an act,
and told its owner his calendar was intact while it was nine rows lighter.

His own words for it, six turns later (i=11064): «items that you did delete without my permission».

## What is pinned here

That the ledger is written at the FUNNEL (so voice, a card button, a worker and cron all land in it), that a
REFUSED action is not written (the same rule V2-707 F0 put on the anti-drag seal), and that the fact reaches
`live_state()` WITH its instruction — V2-453's lesson, paid again in V2-570: a fact with no rule beside it
changes nothing.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import done_ops


@pytest.fixture(autouse=True)
def clean_ledger():
    done_ops.reset()
    yield
    done_ops.reset()


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.agenda import data as ag
    db = ag.load_db()
    # Titles are deliberately UNALIKE: the agenda declares `title` as its row id, so two rows sharing a
    # word make `cancel_meeting` answer `ambiguous` and the generic door correctly does nothing — which
    # would make the case below measure a refusal instead of a write.
    db["meetings"] = [{"id": "a1", "title": "Alpha", "date": "2026-09-17", "allDay": True},
                      {"id": "a2", "title": "Beta", "date": "2026-09-17", "allDay": True},
                      {"id": "a3", "title": "Dentist", "date": "2026-09-17", "startTime": "17:00"}]
    store.save(ag.WIDGET_ID, db)
    return ag


def _run(action, payload):
    from widgets import server_api
    return asyncio.run(server_api.brain_action("agenda", action, payload))


def _live():
    from nucleo.flash import prompt as p
    return p.live_state()


# ── 1 · the funnel writes it ─────────────────────────────────────────────────────────────────────────────

def test_a_sweep_that_RAN_is_in_the_ledger(agenda):
    _run("clear_range", {"from": "2026-09-17", "to": "2026-09-17"})
    rows = done_ops.recent()
    assert [r["action"] for r in rows] == ["clear_range"]
    assert rows[0]["wid"] == "agenda" and rows[0]["destructive"] is True


def test_a_reversible_op_is_recorded_too_but_not_as_destructive(agenda):
    _run("add_meeting", {"title": "New", "date": "2026-09-18", "startTime": "10:00"})
    assert done_ops.recent() and done_ops.recent()[-1]["destructive"] is False
    assert not done_ops.destructive_since()


def test_an_action_the_CONTRACT_refused_never_reaches_the_ledger(agenda):
    """The V2-705 contract answers before the funnel dispatches anything, so nothing can be written."""
    res = _run("cancel_meeting", {})
    assert res.get("ok") is False
    assert not done_ops.recent(), f"a refused action entered the book of what happened: {done_ops.recent()}"


def test_an_action_the_WIDGET_refused_is_not_remembered_as_done(agenda):
    """The same rule V2-707 F0 put on `brain._last_dataop`: a refusal is not an event — and this is the
    path that actually exercises it, because this call gets all the way to `apply_action` and comes back
    `ok: False` instead of being stopped at the door."""
    res = _run("cancel_meeting", {"title": "a meeting that does not exist"})
    assert res.get("ok") is False, res
    assert not done_ops.recent(), f"a refused action entered the book of what happened: {done_ops.recent()}"


def test_cancelling_ONE_meeting_is_destructive_in_the_ledger(agenda):
    """V2-710 T0.1 — THE BOOK ASKED THE WRONG QUESTION. `_note_done` classified with `actions.classify`,
    which answers how much FRICTION an action has, to fill a field that asks whether the action REMOVED
    something. They are different questions and `agenda:cancel_meeting` is where they disagree: it is FAST
    on purpose (V2-707 F1 — one row with a selector and a snapshot runs, N>1 asks by radius), so the book
    recorded the deletion of a real Google Calendar event as `destructive: False` and `done_ops_lines()`
    emitted the mild instruction. That is the V2-707 F6 incident in its ONE-ROW form, which is the normal
    way of deleting an appointment: measured 2026-09-16, `classify=fast` → `destructive=False`.

    The field is filled by `contract.is_destructive`, which answers the question the field asks."""
    _run("cancel_meeting", {"title": "Dentist"})
    rows = done_ops.recent()
    assert rows and rows[-1]["action"] == "cancel_meeting", rows
    assert rows[-1]["destructive"] is True, (
        "cancelling a meeting REMOVES a row (and a real calendar event), so the book has to say so — "
        "asking `actions.classify` here answers how much friction it has, not what it did")
    line = next(l for l in _live().splitlines() if l.startswith("YA EJECUTADO"))
    assert "TIENE RAZÓN" in line, "and the HARD instruction is the one that has to reach the turn"


def test_the_generic_data_door_writes_the_ledger_too(agenda):
    """V2-707 F1's `rows.*` is the path for what nobody declared, and it is still a mutation of his data."""
    _run("rows.delete", {"collection": "meetings", "where": {"allDay": True}, "confirmed": True})
    rows = done_ops.recent()
    assert rows and rows[-1]["action"] == "rows.delete" and rows[-1]["destructive"] is True
    assert rows[-1]["n"] == 2, "the ledger carries HOW MANY rows, which is what he was arguing about"


# ── 2 · it reaches the turn, with its rule ───────────────────────────────────────────────────────────────

def test_the_prompt_says_it_happened(agenda):
    _run("clear_range", {"from": "2026-09-17", "to": "2026-09-17"})
    live = _live()
    assert "YA EJECUTADO SOBRE SUS DATOS" in live
    assert "agenda:clear_range" in live


def test_and_the_instruction_forbids_the_sentence_he_ACTUALLY_heard(agenda):
    """A fact without its rule changes nothing (V2-453). The rule names the exact reasoning that failed:
    deducing from «no confirmation» that nothing was touched."""
    _run("clear_range", {"from": "2026-09-17", "to": "2026-09-17"})
    line = next(l for l in _live().splitlines() if l.startswith("YA EJECUTADO"))
    assert "TIENE RAZÓN" in line
    assert "no se ha tocado nada" in line, "the measured reply has to be forbidden by name"
    assert "confirmación" in line, "and the reasoning behind it named as the wrong thing to reason from"


def test_a_clean_session_carries_no_line_at_all(agenda):
    assert "YA EJECUTADO SOBRE SUS DATOS" not in _live()


def test_a_reversible_op_alone_gets_the_MILD_instruction(agenda):
    """«You deleted my stuff» is not a claim anybody makes about an `add_meeting`, and a prompt that shouts
    on every write teaches the model to ignore the line."""
    _run("add_meeting", {"title": "New", "date": "2026-09-18", "startTime": "10:00"})
    line = next(l for l in _live().splitlines() if l.startswith("YA EJECUTADO"))
    assert "TIENE RAZÓN" not in line and "cuéntalo como hecho" in line


def test_the_ledger_forgets_what_is_no_longer_the_conversation(agenda):
    """Half an hour later he is not asking about this turn, and the prompt must not carry it forever."""
    _run("clear_range", {"from": "2026-09-17", "to": "2026-09-17"})
    assert done_ops.recent()
    assert not done_ops.recent(within_s=0.0)
