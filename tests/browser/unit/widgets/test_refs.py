"""Tests for widgets/refs.py (resolving item references) + agenda date/time parsing (V2-026).

These used to run against the LIVE agenda store, which was wrong twice over: they asserted on the
operator's real tasks (so the assertions broke the moment those tasks changed, and the personal data
had to live in the repo for the suite to pass) and `add_meeting` actually wrote into that real agenda
and then tried to clean up after itself. A test must not depend on, nor mutate, someone's data.

Now every case runs against an isolated store seeded with NEUTRAL fixtures. Same coverage, no personal
data, and nothing survives the test.
"""
import pytest

from widgets import refs, store

# Deliberately generic: two projects and three tasks, with ONE name shared between a project and a task
# ("Atlas" / "Atlas review"). That collision is the whole point of `test_resolve_project_not_samename_task`
# — the field filter has to pick the project, not the task that mentions it.
FIXTURE = {
    "mission": "",
    "user": {"workStart": "09:00", "workEnd": "18:00", "lunchStart": "13:00", "lunchEnd": "14:00",
             "energy": "medium", "wantsExercise": False, "notes": ""},
    "projects": [
        {"id": "atlas", "name": "Atlas", "objective": "Sample project", "status": "active", "priority": 1},
        {"id": "beacon", "name": "Beacon", "objective": "Another sample", "status": "active", "priority": 2},
    ],
    "tasks": [
        {"id": "t_migration", "projectId": "atlas", "title": "Finish the migration", "status": "todo",
         "estimateMinutes": 60, "energy": "high", "priority": 1, "deep": True},
        {"id": "t_atlas_review", "projectId": "atlas", "title": "Atlas review", "status": "todo",
         "estimateMinutes": 30, "energy": "low", "priority": 2, "deep": False},
        {"id": "t_newsletter", "projectId": "beacon", "title": "Draft the newsletter", "status": "todo",
         "estimateMinutes": 45, "energy": "medium", "priority": 3, "deep": False},
    ],
    "ideas": [], "meetings": [], "recurring": [],
}


@pytest.fixture(autouse=True)
def isolated_agenda(tmp_path, monkeypatch):
    """Point the widget store at a throwaway directory and seed it. The real agenda is never read."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save("agenda", dict(FIXTURE))
    yield


def test_id_field_from_manifest():
    # The id field of each action is derived from the payload declared in the agenda's real manifest.
    assert refs.id_field_for_action("agenda", "done") == "taskId"
    assert refs.id_field_for_action("agenda", "drop_project") == "projectId"
    assert refs.id_field_for_action("agenda", "add_meeting") is None   # creates an item → nothing to resolve


def test_resolve_task_by_natural_language():
    r = refs.resolve("agenda", "done", "the migration task")
    assert r.ok and r.payload["taskId"] == "t_migration"
    r2 = refs.resolve("agenda", "snooze", "the newsletter one")
    assert r2.ok and r2.payload["taskId"] == "t_newsletter"


def test_resolve_project_not_samename_task():
    # "Atlas" is both a project and part of a task title ("Atlas review"); drop_project→projectId must
    # point at the PROJECT, not the task. The field filter is what guarantees it.
    r = refs.resolve("agenda", "drop_project", "the Atlas project")
    assert r.ok and r.payload["projectId"] == "atlas"


def test_add_meeting_needs_no_ref():
    r = refs.resolve("agenda", "add_meeting", "")
    assert r.ok                                     # nothing to resolve


def test_no_match_asks_not_invents():
    r = refs.resolve("agenda", "done", "something that does not exist at all zzz")
    assert not r.ok and r.needs in ("no_match", "ambiguous") and r.candidates


def test_respects_a_real_given_id():
    r = refs.resolve("agenda", "done", "", {"taskId": "t_migration"})
    assert r.ok and r.payload["taskId"] == "t_migration"


def test_items_line_lists_live_items():
    line = refs.items_line("agenda")
    assert "items ahora" in line and "migration" in line.lower()


# ── spoken dates/times (agenda) ────────────────────────────────────────────────────────────────────────
def test_agenda_relative_dates_and_times():
    import time

    from widgets.agenda import data as a
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    assert a._resolve_date("mañana") == tomorrow
    assert a._resolve_date("hoy") == today
    assert a._resolve_date("2026-08-01") == "2026-08-01"
    assert a._resolve_date("") == today
    assert a._resolve_time("cinco") == "17:00"          # no am/pm, 1–7 → afternoon
    assert a._resolve_time("9 de la mañana") == "09:00"
    assert a._resolve_time("17:00") == "17:00"


def test_agenda_add_meeting_persists_normalized():
    """Used to add a meeting to the operator's REAL agenda and delete it afterwards — a test that edits
    live data is one failed assertion away from leaving it edited."""
    import time

    from widgets.agenda import data as a
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    assert a.load_db().get("meetings") == []
    a.apply_action("add_meeting", {"title": "Dentist", "date": "mañana", "startTime": "cinco"})
    ms = a.load_db().get("meetings", [])
    assert len(ms) == 1
    assert ms[0]["date"] == tomorrow and ms[0]["startTime"] == "17:00" and ms[0]["title"] == "Dentist"
