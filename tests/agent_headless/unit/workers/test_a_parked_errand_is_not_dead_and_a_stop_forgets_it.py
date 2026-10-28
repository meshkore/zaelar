"""A parked errand (`quota_wait.park`, 2026-10-11) is NOT dead and IS work. Two consequences, each a reader that had
to learn it: the V2-222 death note («ha MUERTO … no se va a reintentar sola») would now be false, so it is not
pushed for a parked goal; and «para todo» / Reset / a stop that names it cancel the parked job — otherwise a stop he
ordered would come back at the reset hour as «retomo …»."""
import time

import pytest

from nucleo import dispatch
from nucleo.pulse import scheduler
from nucleo.workers import ended, providers, quota_wait
from nucleo.workers.session import SessionRecord
from voice import brain_notes

GOAL = "Busca un sofá de tres plazas en Barcelona por menos de 600 euros"


@pytest.fixture
def parked(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: time.time() + 3600)
    monkeypatch.setattr(quota_wait, "_PARKS", {})
    for e in quota_wait._parked_jobs():
        scheduler.cancel(str(e["id"]))
    brain_notes.drain()
    assert quota_wait.park(GOAL)
    yield
    quota_wait.forget("")
    brain_notes.drain()


def _ended(goal):
    rec = SessionRecord(task_id=f"e{abs(hash(goal)) % 999}", goal=goal, kind="research")
    rec.status, rec.ok, rec.result_summary = "error", False, "quota"
    ended._remember_ended(rec)
    return [n for n in brain_notes.drain() if "MUERTO" in n]


def test_a_parked_goal_gets_no_death_note(parked):
    assert _ended(GOAL) == []


def test_an_unparked_death_still_gets_it(parked):
    assert _ended("Find me a plumber for Thursday")


def test_a_stop_naming_it_forgets_it(parked):
    dispatch.cancel_soon("para lo del sofá")
    assert not quota_wait.is_parked(GOAL)


def test_a_stop_naming_something_else_keeps_it(parked):
    dispatch.cancel_soon("para lo del fontanero")
    assert quota_wait.is_parked(GOAL)


def test_a_reset_forgets_every_parked_errand(parked):
    from nucleo import reset
    reset.abandon_work(source="test")
    assert not quota_wait.is_parked(GOAL)
