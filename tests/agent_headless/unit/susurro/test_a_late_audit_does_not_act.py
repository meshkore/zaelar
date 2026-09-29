#
# test_a_late_audit_does_not_act.py — 2026-09-29, session 81095d8d.
#
# The auditor's window is composed when the friction fires; the memory reads and the model took 25 s. In those
# 25 s the operator said three more turns, the fast brain ran `youtube:search` and `youtube:follow_channel`, and
# he heard «There you go». The audit then came back with a `worker_action` written against the frozen window —
# «the fast brain never searched beyond his contacts» — and a Brain Worker spent $0.89 finding the man he had
# just subscribed to, in a second card beside the video widget. Right about the tramo it saw, wrong about the
# present. An action or a spoken repair drawn from a stale window is dropped; a finding still lands.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/susurro/test_a_late_audit_does_not_act.py
#
import time

import pytest

from nucleo import done_ops
from nucleo.susurro import apply as sapply
from nucleo.susurro import engine as sengine

WORKER = ("Search for a person named 'Jose Luis Carpatos' for Richard: look beyond his phone contacts "
          "(public/web sources) and report back any match or a clear negative result.")
REPAIR = "My mistake, Richard — let me actually search for Jose Luis Carpatos, including anyone outside your contacts."


@pytest.fixture(autouse=True)
def _clean():
    done_ops.reset()
    sengine._TURN_RING.clear()
    yield
    done_ops.reset()
    sengine._TURN_RING.clear()


# ── what counts as «the conversation moved» ──────────────────────────────────────────────────────────────

def test_nothing_happened_reads_zero():
    t0 = time.time()
    assert sengine._advanced_since(t0) == 0


def test_a_turn_of_his_after_the_window_counts():
    t0 = time.time()
    sengine._TURN_RING.append({"user": "No. No. But I want to look for this guy in YouTube", "ts": t0 + 1})
    assert sengine._advanced_since(t0) == 1


def test_a_widget_op_that_ran_after_the_window_counts():
    t0 = time.time() - 1
    done_ops.note("youtube", "search", {"query": "Jose Luis Carpatos"})
    done_ops.note("youtube", "follow_channel", {"name": "José Luis Cárpatos"})
    assert sengine._advanced_since(t0) == 2


def test_what_happened_BEFORE_the_window_does_not_count():
    done_ops.note("youtube", "play_result", {})
    sengine._TURN_RING.append({"user": "earlier", "ts": time.time() - 10})
    t0 = time.time()
    assert sengine._advanced_since(t0) == 0


# ── and what the applier does with it ───────────────────────────────────────────────────────────────────

def test_a_stale_worker_action_and_repair_are_dropped_but_the_finding_lands(monkeypatch, tmp_path):
    from nucleo import dispatch
    from nucleo.flash import escalate
    from voice import brain_notes
    launched: list = []
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, **kw: launched.append(req) or 9)
    brain_notes.drain()
    finding = {"type": "finding", "severity": "P2", "area": "prompt", "title": "operator name drifts",
               "detail": "Richard → Carlos", "proposal": "one name"}
    recs = sapply.apply_corrections(
        [{"type": "repair_say", "text": REPAIR},
         {"type": "worker_action", "request": WORKER, "reason": "r"},
         finding],
        reason="petición repetida (no atendida)", window=WORKER, advanced=3,
        findings_path=str(tmp_path / "f.jsonl"))
    assert launched == [], "a worker drawn from a stale window must not start"
    assert not any(REPAIR in n for n in brain_notes.drain()), "nor may the stale repair be spoken"
    by_type = {r["type"]: r for r in recs}
    assert by_type["worker_action"]["ok"] is False and by_type["worker_action"]["stale"] == 3
    assert by_type["repair_say"]["ok"] is False
    assert by_type["finding"]["ok"] is True


def test_a_fresh_window_still_acts(monkeypatch):
    """The other direction — otherwise «drop everything» would pass the test above."""
    from nucleo import dispatch
    from nucleo.flash import escalate
    launched: list = []
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, **kw: launched.append(req) or 9)
    recs = sapply.apply_corrections([{"type": "worker_action", "request": WORKER, "reason": "r"}],
                                    reason="r", window=WORKER, advanced=0)
    assert launched == [WORKER] and recs[0]["ok"] is True
