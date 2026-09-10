"""Agenda suite isolation — the SCHEDULER half (V2-652).

A unit test must never touch live artifacts. Every file here already isolates the widget STORE
(`store.DATA_DIR` → tmp_path), but `add_meeting`'s default reminder (V2-473) reaches
`nucleo.scheduler.create`, which persists into `memory.journal` — the operator's REAL `zaelar.db`,
because nothing in the test conftests overrides `ZAELAR_DB`.

This stayed invisible for a reason worth keeping: the older agenda tests use PAST dates, and
`_schedule_reminder` refuses an instant that already passed («el instante ya pasó») — so they never
wrote a job by ACCIDENT, not by design. The first test file with FUTURE dates
(`test_the_write_does_not_invent_an_hour.py`, 2026-09-10) left 18 orphan «aviso: Cita Agencia
Tributaria» jobs in the operator's live cron across its runs and disarms; they were cured by hand the
same day.

The fake keeps the reminder LOGIC measurable (a scheduled add still gets a `reminder_id`) while the
write lands in this in-memory ledger instead of anybody's database.
"""
import pytest


@pytest.fixture(autouse=True)
def _scheduler_never_touches_the_live_journal(monkeypatch):
    from nucleo import scheduler

    jobs: dict[str, dict] = {}
    seq = {"n": 0}

    def _create(prompt, schedule, name="", repeat="", now=None):
        seq["n"] += 1
        jid = f"test-{seq['n']}"
        jobs[jid] = {"prompt": prompt, "schedule": schedule, "name": name}
        return {"ok": True, "id": jid, "schedule": schedule, "error": None, "display": schedule}

    def _cancel(ref):
        return jobs.pop(str(ref), None) is not None

    monkeypatch.setattr(scheduler, "create", _create)
    monkeypatch.setattr(scheduler, "cancel", _cancel)
    return jobs
