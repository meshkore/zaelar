"""The model's `cron.create` notice never lands a week past the deadline, nor in the past (2026-10-14).

`remember-and-remind-deadline` (ES, Wednesday 2026-10-14 ~12:00): «Apúntame que el jueves tengo que renovar el
seguro del coche, y recuérdamelo el miércoles». The model's tag said today 09:00 — already gone — and
`safe_reminder_schedule` «corrected» it to what «el miércoles» means in isolation: 2026-10-21 09:00, six days AFTER
Thursday. The same door now applies the backstop's rule (`reminder_before`): before the commitment, and an hour gone
today rings soon today. Both channels go through it — the probe with the reply, the voice provider without it.
Frozen clock; `list_jobs` is a double, nothing is scheduled.
"""
from __future__ import annotations

import time

import pytest

from nucleo.pulse import notice_today as NT
from nucleo.pulse import scheduler as S
from nucleo.flash import reminder_guards as R

NOON = time.mktime((2026, 10, 14, 12, 0, 0, 0, 1, -1))     # Wednesday
DAWN = time.mktime((2026, 10, 14, 7, 30, 0, 0, 1, -1))
ASK = "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles."
REPLY = "Vale, el jueves 15 tienes la renovación del seguro del coche y te aviso el miércoles 14 a las 9."
ASK_EN = "Make a note that on Thursday I have to renew the car insurance, and remind me on Wednesday."


@pytest.fixture(autouse=True)
def _frozen(monkeypatch):
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: [])
    NT.take_move(NOON, within_s=1e12)


def _at(monkeypatch, now):
    monkeypatch.setattr(S.time, "time", lambda: now)


def test_the_measured_tag_rings_today_not_next_wednesday(monkeypatch):
    _at(monkeypatch, NOON)
    assert R.safe_reminder_schedule("2026-10-14 09:00", REPLY, ASK) == "2026-10-14 13:00"
    assert NT.take_move(NOON)["at"] == "2026-10-14 13:00", "the move is noted for the reply to read back"


def test_the_voice_path_without_the_reply_rings_today_too(monkeypatch):
    _at(monkeypatch, NOON)
    assert R.safe_reminder_schedule("2026-10-14 09:00", "", ASK_EN) == "2026-10-14 13:00"
    assert R.safe_reminder_schedule("Wednesday", "", ASK_EN) == "2026-10-14 13:00", "next week is after the deadline"


def test_in_the_morning_the_asked_hour_stands(monkeypatch):
    _at(monkeypatch, DAWN)
    assert R.safe_reminder_schedule("2026-10-14 09:00", REPLY, ASK) == "2026-10-14 09:00"
    assert R.safe_reminder_schedule("el miércoles", "", ASK) == "2026-10-14 09:00"


def test_the_prose_backstop_says_the_same_instant(monkeypatch):
    _at(monkeypatch, NOON)
    assert R.dated_reminder_backstop(REPLY, ASK)["schedule"] == "2026-10-14 13:00"


def test_a_cadence_the_models_own_future_instant_and_no_deadline_are_untouched(monkeypatch):
    _at(monkeypatch, NOON)
    assert R.safe_reminder_schedule("2026-10-21 09:00", "", ASK) == "2026-10-21 09:00", "its own reading stands"
    assert R.safe_reminder_schedule("every 30m", "", "avísame cada media hora") == "every 30m"
    assert R.safe_reminder_schedule("2026-10-20 18:00", "", "recuérdame el martes llamar a Juan") == "2026-10-20 18:00"
