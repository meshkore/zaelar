"""A standalone notice is bounded by its slots, never by his words (refactor2710-06 T-06, from `reminder_guards`).

The model fills `notice_at` / `before` / `commitment_at` / `commitment`; the agenda only bounds the consequence: never
after the thing, an hour gone today rings soon, a day gone schedules nothing, and the job tells the agent to NOTIFY.
"""
from __future__ import annotations

import datetime as dt

from widgets.agenda import notice

NOW = dt.datetime(2026, 10, 28, 12, 0)          # a Wednesday, noon


def test_an_absolute_instant_before_the_thing_is_kept():
    out = notice.bound({"notice_at": "2026-10-28 18:00", "commitment_at": "2026-10-29 09:00"}, NOW)
    assert out == {"verdict": "met", "at": "2026-10-28 18:00", "why": ""}


def test_an_offset_is_counted_from_the_thing():
    out = notice.bound({"before": "-PT30M", "commitment_at": "2026-10-29T09:00"}, NOW)
    assert out["verdict"] == "met" and out["at"] == "2026-10-29 08:30"
    assert notice.bound({"before": "-P1D", "commitment_at": "2026-11-02 10:00"}, NOW)["at"] == "2026-11-01 10:00"


def test_a_notice_after_the_thing_is_asked_never_moved():
    """V2-167: «remind me on Wednesday» for a Thursday deadline must not ring the Wednesday after."""
    out = notice.bound({"notice_at": "2026-11-04 09:00", "commitment_at": "2026-10-29 09:00"}, NOW)
    assert out["verdict"] == "asked" and not out["at"]


def test_an_hour_gone_today_rings_soon_and_a_day_gone_schedules_nothing():
    assert notice.bound({"notice_at": "2026-10-28 09:00"}, NOW)["at"] == "2026-10-28 12:05"
    assert notice.bound({"notice_at": "2026-10-27 09:00"}, NOW)["verdict"] == "cannot"


def test_a_missing_slot_is_asked_never_guessed():
    assert notice.bound({}, NOW)["verdict"] == "asked"
    assert notice.bound({"before": "-PT30M"}, NOW)["verdict"] == "asked", "an offset with nothing to count from"
    assert notice.bound({"notice_at": "next wednesday"}, NOW)["verdict"] == "asked", "words are not a slot"


def test_the_job_tells_the_agent_to_notify():
    assert notice.prompt_for({"commitment": "renew the car insurance"}).startswith("AVISA al operador")
    assert notice.prompt_for({}) == ""


def test_the_door_bounds_a_one_off_and_leaves_a_cadence_alone():
    made = []

    def create(prompt, when, name="", repeat=""):
        made.append((prompt, when))
        return {"ok": True}
    r, v = notice.schedule(create, {"schedule": "every 30m", "prompt": "check the oven"})
    assert v == "started" and made[-1] == ("check the oven", "every 30m"), "a cadence is the model's own"
    r, v = notice.schedule(create, {"schedule": "2020-01-01 09:00", "prompt": "renew the insurance"})
    assert v == "cannot" and not r["ok"] and len(made) == 1, "a day gone schedules nothing"
    r, v = notice.schedule(create, {"notice_at": "2099-01-01 09:00", "prompt": "I have to renew the insurance"})
    assert v == "met" and made[-1] == ("AVISA al operador, es el recordatorio que te pidió: I have to renew the "
                                       "insurance", "2099-01-01 09:00")


def test_add_reminder_is_the_agendas_own_action(monkeypatch):
    """The standalone notice is `add_reminder` of the agenda: no moment → asked; a moment → on the scheduler."""
    from nucleo.pulse import scheduler
    from widgets.agenda import data
    made = []
    monkeypatch.setattr(scheduler, "create", lambda prompt, when, name="", repeat="":
                        made.append((prompt, when)) or {"ok": True, "display": when})
    out = data.apply_action("add_reminder", {"commitment": "renew the insurance"})
    assert out.get("verdict") == "asked" and not made
    out = data.apply_action("add_reminder", {"notice_at": "2099-03-04 09:00", "commitment": "renew the insurance"})
    assert out.get("ok") and made == [("AVISA al operador, es el recordatorio que te pidió: renew the insurance",
                                       "2099-03-04 09:00")]


def test_offsets_read_only_iso_durations():
    assert notice.offset_s("-PT1H30M") == -5400 and notice.offset_s("P2D") == 172800
    assert notice.offset_s("-30m") is None and notice.offset_s("PT") is None and notice.offset_s("P1H") is None
