"""«Note it for Thursday and remind me on Wednesday» schedules a notice ON Wednesday (V2-781 T513, 2026-10-03).

Measured in the use-case pair `remember-and-remind-deadline` (ES + EN): both replies claimed the Wednesday
notice and neither scheduled one. EN sent an undeclared `reminder` key inside `add_meeting` (dropped, only the
default ~2 h notice on Thursday existed); ES wrote an all-day item plus a SECOND all-day entry named «Aviso»,
and an all-day item could not carry a notice at all (`_schedule_reminder` needed a start hour even with `at`).
The contract now has one declared field for «the notice goes on THIS day», and an all-day item can hold one.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from widgets.agenda import data as agenda

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


@pytest.fixture
def fake_sched(monkeypatch):
    from nucleo import scheduler
    calls = {"created": [], "cancelled": []}

    def _create(prompt, stamp, name="", origin="cron"):
        calls["created"].append((prompt, stamp, name))
        return {"ok": True, "id": f"job{len(calls['created'])}"}

    monkeypatch.setattr(scheduler, "create", _create)
    monkeypatch.setattr(scheduler, "cancel", lambda ref: calls["cancelled"].append(ref))
    return calls


def _in_days(n: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


THU, WED = _in_days(5), _in_days(4)


def _live_stamps(calls) -> list[str]:
    live = [f"job{i + 1}" for i in range(len(calls["created"]))]
    return [calls["created"][i][1] for i, j in enumerate(live) if j not in calls["cancelled"]]


def test_an_all_day_item_reminded_the_day_before_rings_that_day(fake_sched):
    r = agenda.apply_action("add_meeting", {"title": "Renovar el seguro del coche", "date": THU, "remind": WED})
    assert r.get("ok") is not False, r
    (m,) = agenda.load_db()["meetings"]
    assert m.get("allDay") and m.get("reminder_id"), m
    assert [s[:10] for s in _live_stamps(fake_sched)] == [WED]
    assert str(m.get("remindAt", "")).startswith(WED)


def test_a_timed_item_reminded_the_day_before_rings_at_its_own_hour_and_only_once(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Renew car insurance", "date": THU, "startTime": "09:00",
                                        "remind": WED})
    assert _live_stamps(fake_sched) == [f"{WED} 09:00"], "the asked notice replaces the default ~2 h one"


def test_the_key_the_model_sent_live_is_read_not_dropped(fake_sched):
    r = agenda.apply_action("add_meeting", {"title": "Renew car insurance", "date": THU, "startTime": "09:00",
                                            "reminder": f"{WED} 18:30"})
    assert "reminder" not in (r.get("ignored") or []), r
    assert _live_stamps(fake_sched) == [f"{WED} 18:30"]


def test_set_reminder_reaches_an_all_day_item(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Renovar el seguro", "date": THU})
    assert fake_sched["created"] == [], "an all-day item gets no default notice"
    r = agenda.apply_action("set_reminder", {"title": "seguro", "at": WED})
    assert r.get("ok") is not False, r
    assert [s[:10] for s in _live_stamps(fake_sched)] == [WED]
    r = agenda.apply_action("set_reminder", {"title": "seguro", "at": f"{WED} 20:00"})
    assert r.get("ok") is not False, r
    assert _live_stamps(fake_sched) == [f"{WED} 20:00"]


def test_the_card_declares_the_field_and_says_it_is_never_a_second_entry():
    acts = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))["actions"]
    assert "remind" in acts["add_meeting"]["payload"]
    assert "YYYY-MM-DD" in acts["set_reminder"]["payload"]["at"]
    assert "remind" in acts["add_meeting"]["how"]
