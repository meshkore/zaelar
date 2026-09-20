"""V2-728 F6 — a scheduled job is a commission with a clock on it, and it shows on the same board.

«Periódicas» and «Programadas» are two lists, not one. Before this they were the same tab, so «enséñame las
tareas programadas» opened the things that REPEAT — the wrong list, with no error to notice it by.

The scheduler keeps storing where it stores (see `nucleo/tasks.scheduled_mirrored` for why the move was not
worth the risk); what is fixed here is that the board follows it at every point the job changes.
"""
import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import scheduler, tasks as T


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _rows(mode):
    return T.board(mode)


def test_a_weekly_job_lands_in_PERIODICAS(fresh_db):
    r = scheduler.create("mira si hay concierto de Shakira", "every 7d", name="conciertos de Shakira")
    assert r["ok"]
    rows = _rows("recurring")
    assert [x["title"] for x in rows] == ["conciertos de Shakira"]
    assert rows[0]["mode"] == "recurring" and rows[0]["state"] == "pending"
    assert rows[0]["schedule"]["display"] and rows[0]["schedule"]["next_run"] > 0
    assert _rows("scheduled") == []            # …and NOT in the other list


def test_a_one_shot_lands_in_PROGRAMADAS(fresh_db):
    scheduler.create("llama al dentista", "2026-09-28 09:00", name="llamar al dentista")
    rows = _rows("scheduled")
    assert [x["title"] for x in rows] == ["llamar al dentista"]
    assert rows[0]["mode"] == "scheduled"
    assert _rows("recurring") == []


def test_a_five_field_cron_is_periodic_too(fresh_db):
    scheduler.create("resumen", "0 9 * * 1", name="resumen del lunes")
    assert [x["title"] for x in _rows("recurring")] == ["resumen del lunes"]


def test_firing_a_recurring_job_moves_its_next_moment_and_keeps_it_listed(fresh_db):
    r = scheduler.create("mira los conciertos", "every 1h", name="conciertos")
    first = _rows("recurring")[0]["schedule"]["next_run"]
    entry = scheduler.due(now=first + 1)[0]
    scheduler.mark_fired(entry, now=first + 1)
    row = _rows("recurring")[0]
    assert row["schedule"]["next_run"] > first, "the board still shows the moment that has already passed"
    assert row["state"] == "pending"


def test_firing_a_one_shot_takes_it_off_the_waiting_list(fresh_db):
    scheduler.create("llama al dentista", "30m", name="dentista")
    entry = scheduler.due(now=_rows("scheduled")[0]["schedule"]["next_run"] + 1)[0]
    scheduler.mark_fired(entry, now=entry["detail"]["schedule"]["next_run"] + 1)
    assert _rows("scheduled") == []
    # …and it is not lost: a one-shot that fired is DONE, which is a different word from cancelled.
    done = ts.tasks_where(states=ts.DONE_STATES, modes=("scheduled",))
    assert len(done) == 1 and done[0]["state"] == "done"


def test_cancelling_a_recurring_job_says_cancelled_not_done(fresh_db):
    """«Lo hice» and «ya no lo hago» are different answers, and a list that conflates them cannot be read."""
    scheduler.create("mira los conciertos", "every 7d", name="conciertos")
    assert scheduler.cancel("conciertos") is True
    assert _rows("recurring") == []
    gone = ts.tasks_where(states=ts.DONE_STATES, modes=("recurring",))
    assert len(gone) == 1 and gone[0]["state"] == "cancelled"


def test_the_jobs_that_existed_BEFORE_the_board_are_put_on_it(fresh_db, monkeypatch):
    """The reconcile at startup. Without it a weekly reminder created last month is invisible for a week —
    a “Periódicas” tab that lies by being empty, which is the worst way for this to fail."""
    import nucleo.tasks as _t
    monkeypatch.setattr(_t, "scheduled_mirrored", lambda *_a, **_k: None)   # the board did not exist yet
    scheduler.create("mira los conciertos", "every 7d", name="conciertos")
    scheduler.create("llama al dentista", "2026-09-28 09:00", name="dentista")
    monkeypatch.undo()
    assert _rows("recurring") == [] and _rows("scheduled") == []
    assert scheduler.reconcile_board() == 2
    assert [x["title"] for x in _rows("recurring")] == ["conciertos"]
    assert [x["title"] for x in _rows("scheduled")] == ["dentista"]


def test_reconcile_is_idempotent(fresh_db):
    scheduler.create("mira los conciertos", "every 7d", name="conciertos")
    scheduler.reconcile_board()
    scheduler.reconcile_board()
    assert len(_rows("recurring")) == 1, "reconciling twice duplicated the row"


def test_a_timed_job_never_shows_up_in_the_live_list(fresh_db):
    """«En curso» is what the agent is doing RIGHT NOW. A weekly job that is not running is not that."""
    scheduler.create("mira los conciertos", "every 7d", name="conciertos")
    assert T.board("live") == []


# ── and the CALENDAR sees them, without seeing an appointment twice ─────────────────────────────────────
def test_the_calendar_marks_the_systems_own_timed_work(fresh_db):
    """«Si te digo la semana que viene, haz esto… se puede ver perfectamente en la agenda, aunque es una
    tarea no para nosotros, sino para el sistema» (operator, 2026-09-20)."""
    from widgets.agenda import system_tasks as ST
    scheduler.create("mira el precio del monitor", "every 7d", name="precio del monitor")
    rows = ST.system_tasks(db={"meetings": []})
    assert [r["title"] for r in rows] == ["precio del monitor"]
    assert rows[0]["recurring"] is True and rows[0]["date"] and rows[0]["startTime"]


def test_an_APPOINTMENTS_OWN_NOTICE_is_not_marked_a_second_time(fresh_db):
    """The subtlety that makes the band usable. Every meeting schedules its own alarm, which is a scheduled
    task like any other — drawn here it would put a second mark on a day that already shows the appointment.

    The filter is the RELATIONSHIP, not a flag: the meeting stores the job id it got back as `reminder_id`,
    so the join already exists in the data and does not depend on anybody having remembered to declare
    anything. Measured against the operator's real database while this was being written: NINE «aviso:
    Dentist» rows predate `scheduler.create(origin=…)` entirely and carry no origin at all — a filter built
    on the flag alone would have marked every one of his appointments twice.
    """
    from widgets.agenda import system_tasks as ST
    r = scheduler.create("Recuérdale la cita", "2026-09-28 09:00", name="aviso: Dentista", origin="agenda")
    scheduler.create("mira el precio del monitor", "every 7d", name="precio del monitor")

    # (a) the flag path, for jobs created from today on
    assert [x["title"] for x in ST.system_tasks(db={"meetings": []})] == ["precio del monitor"]

    # (b) the JOIN path, which is what covers every job written before the flag existed
    legacy = scheduler.create("Recuérdale la otra cita", "2026-09-29 09:00", name="aviso: Médico")
    db = {"meetings": [{"title": "Médico", "reminder_id": str(legacy["id"])}]}
    titles = [x["title"] for x in ST.system_tasks(db=db)]
    assert "aviso: Médico" not in titles, (
        "a legacy notice with no declared origin was marked on the calendar — the appointment it belongs "
        "to is already there, and this is the duplication the join exists to prevent")
    assert "precio del monitor" in titles, "…and a real standing cron must still be marked"
    assert r["ok"]
