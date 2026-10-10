"""A notice the agent SPEAKS after the tester's last line is part of the conversation (V2-781).

Measured in `knows-who-i-am-without-being-told-again__us` (2026-10-10): the tester's last line was at 135 s,
the worker's notice «Your three quick gluten-free dinners are ready on screen…» was spoken at 330 s, and the
judge scored «never said» because the transcript it reads stops at the last turn. In production that notice
reaches the operator by voice; the round has to show it to the judge, marked as unprompted.
"""
from tests.use_cases.e2e.agent import verify


def _ev(ts, kind, text, role="assistant"):
    return {"ts_ms": ts, "kind": kind, "role": role, "text": text}


def test_a_notice_after_the_last_turn_is_returned():
    evs = [_ev(1000, "notify", "early"), _ev(5000, "notify", "Your dinners are ready"),
           _ev(6000, "task", "worker noise")]
    assert verify.late_notices(evs, after_ms=2000) == ["Your dinners are ready"]


def test_only_spoken_agent_notices_count():
    evs = [_ev(5000, "notify", "x", role="system"), _ev(5000, "notify", "  "), _ev(5000, "brain", "y")]
    assert verify.late_notices(evs, after_ms=0) == []


def test_the_round_appends_it_to_the_transcript():
    import inspect
    from tests.use_cases.e2e.agent import run
    assert "late_notices(" in inspect.getsource(run)
