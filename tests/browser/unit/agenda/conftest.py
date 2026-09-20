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

    # The signature is FIXED on purpose — a `**kwargs` double accepts anything and stops being able to
    # notice that the real function changed shape. It earned that keep on 2026-09-20 (V2-728): `origin` was
    # added to `scheduler.create` and this double raised TypeError, which `_schedule_reminder` swallows in
    # its own `except Exception` — so NINE tests went red on «no reminder was created», with nothing
    # anywhere naming the cause. `origin` is recorded rather than ignored, so the distinction it carries
    # (an appointment's own notice vs a standing cron) is assertable here.
    def _create(prompt, schedule, name="", repeat="", now=None, origin="cron"):
        seq["n"] += 1
        jid = f"test-{seq['n']}"
        jobs[jid] = {"prompt": prompt, "schedule": schedule, "name": name, "origin": origin}
        return {"ok": True, "id": jid, "schedule": schedule, "error": None, "display": schedule}

    def _cancel(ref):
        return jobs.pop(str(ref), None) is not None

    monkeypatch.setattr(scheduler, "create", _create)
    monkeypatch.setattr(scheduler, "cancel", _cancel)
    return jobs


@pytest.fixture(autouse=True)
def _the_suite_never_touches_the_operators_real_google_account(tmp_path, monkeypatch):
    """The CONNECTOR half of the same rule, and it cost the operator his first real connection (V2-689).

    `test_the_agenda_owns_its_google_connector.py` calls `apply_action("disconnect")` as a counterweight —
    a perfectly good test of the rule that disconnecting must not open a connect screen. What nobody noticed
    is that it reached `connectors/calendar/oauth.forget()` against the REAL
    `.meshkore/credentials/calendar_oauth.json`. The connector's OWN suite isolates that store on its first
    line; these tests never did.

    It was invisible for exactly one reason: until 2026-09-14 there was no Google account to delete, so
    `forget()` removed nothing every single time. The hour he finally linked one, a routine run of this
    directory unlinked it — and the failure looked like the connector dropping his token, which is the worst
    possible place to go looking. The 233 orphan `pending` records his store had collected are from the same
    source: every `connect` case here minted one in his real file.

    ⚠️ **An unisolated test does not fail — it leaves something behind**, and what it leaves behind may be
    the thing the operator spent an afternoon getting. Third payment of this class after V2-673 (`v2.json`)
    and V2-684 (`zaelar.db`); the shape never changes, only which live store had not been reached yet.
    """
    for mod in ("connectors.calendar.oauth", "connectors.video.oauth", "connectors.photos.oauth",
                "connectors.files.oauth", "connectors.email.oauth"):
        try:
            m = __import__(mod, fromlist=["oauth"])
        except Exception:                              # noqa: BLE001 — a connector absent from this build
            continue
        monkeypatch.setattr(m, "STORE", tmp_path / f"{mod.split('.')[1]}_oauth.json", raising=False)
