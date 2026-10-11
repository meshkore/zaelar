"""`weekend-motor-events__us` / `search-buy-sofa__es` (2026-10-11): «dale un toque cuando el quota se reabra» →
«Done.» / «Te avisaré justo a las 21:11» with `scheduled_jobs.created` EMPTY. The reset hour was known — the
cooldown store has it — and nothing acted on it. Now an errand the asleep chain refuses (dispatcher) or kills
(worker relay with no tier left) becomes a durable scheduled job at the reset, and its ending SAYS so: a promise
with the job behind it."""
import time

import pytest

from nucleo import scheduler
from nucleo.workers import providers, quota_wait

GOAL = "Find me a used surfboard, around 6 feet, for under $275."


@pytest.fixture
def asleep(monkeypatch):
    until = time.time() + 2 * 3600
    monkeypatch.setattr(providers, "exhausted_until", lambda: until)
    monkeypatch.setattr(quota_wait, "_PARKS", {})
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    for e in quota_wait._parked_jobs():
        scheduler.cancel(str(e["id"]))
    return until


def _jobs():
    return [j for j in scheduler.list_jobs() if quota_wait.takes(_detail(j["id"]))]


def _detail(jid):
    from memory import journal
    return (journal.get(int(jid)) or {}).get("detail") or {}


def test_a_refused_errand_becomes_a_job_at_the_reset_and_its_ending_promises_it(asleep):
    summary = quota_wait.parked_summary(GOAL, {"kind": "research"}, "stuck")
    jobs = _jobs()
    assert len(jobs) == 1
    assert abs(jobs[0]["next_run"] - (asleep + quota_wait.FIRE_MARGIN_S)) < 61
    assert _detail(jobs[0]["id"])["resume_errand"] == GOAL
    assert time.strftime("%H:%M", time.localtime(asleep)) in summary and "pick it up again" in summary


def test_the_same_errand_is_parked_once(asleep):
    quota_wait.park(GOAL)
    quota_wait.park(GOAL)
    assert len(_jobs()) == 1 and quota_wait.is_parked(GOAL)


def test_a_reset_that_keeps_lying_is_parked_a_bounded_number_of_times(asleep):
    for _ in range(quota_wait.MAX_PARKS):
        assert quota_wait.park(GOAL)
        quota_wait.forget("")
    assert not quota_wait.park(GOAL)
    assert quota_wait.parked_summary(GOAL, {}, "stuck") == "stuck", "no job → no promise"


def test_an_awake_chain_parks_nothing(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: 0.0)
    assert quota_wait.parked_summary(GOAL, {}, "the old ending") == "the old ending"


def test_a_worker_killed_with_no_tier_left_is_parked_too(asleep):
    from nucleo.workers.relay import relay_out_of_fuel
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="t9", goal=GOAL, kind="research")
    rec.provider_down = {"provider": "deepseek", "next": "", "text": "402 Insufficient Balance"}
    relay_out_of_fuel(rec, 2)
    assert rec.ok is False and quota_wait.is_parked(GOAL)
    assert "pick it up again" in rec.result_summary


def test_the_dispatcher_parks_the_errand_it_refuses_and_says_so(asleep, monkeypatch):
    import asyncio
    from nucleo import dispatch, dispatch_session
    from nucleo.workers.session import SessionRecord
    said = []

    async def _deliver(rec):
        said.append(rec.result_summary)
    monkeypatch.setattr(dispatch, "_deliver_confirm", _deliver)
    _tell = quota_wait.tell
    monkeypatch.setattr(quota_wait, "tell", lambda rec, deliver: _tell(rec, deliver, settle_s=0))
    monkeypatch.setitem(dispatch._SESSIONS, "q1", SessionRecord(task_id="q1", goal=GOAL, kind="research"))
    task = dispatch.Task(id="q1", request=GOAL, kind="research", trusted=False)
    asyncio.new_event_loop().run_until_complete(dispatch_session._run_session(task))
    assert quota_wait.is_parked(GOAL)
    assert said and "pick it up again" in said[0]


def test_after_the_turn_said_the_quota_the_note_only_adds_the_resume(asleep):
    import asyncio
    from types import SimpleNamespace
    quota_wait.park(GOAL)
    quota_wait.asleep_line()                      # the turn's own wait line, just said
    said = []

    async def _deliver(rec):
        said.append(rec.result_summary)
    rec = SimpleNamespace(goal=GOAL, result_summary="the full ending")
    asyncio.new_event_loop().run_until_complete(quota_wait.tell(rec, _deliver, settle_s=0))
    assert said and said[0] != "the full ending" and "quota" not in said[0].lower()
