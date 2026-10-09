"""A worker's notice at an instant that already rings is not a second notice (V2-781 pair 3, 2026-10-10).

ES round: «avísame el día del estreno» → the turn's backstop scheduled 2026-10-30 09:00; three minutes later the
Brain Worker, verifying the date, scheduled its own «¡Hoy es el día!» at the SAME instant. Two alarms for one ask.
The worker's door asks the scheduler for the instant first; a live job there answers it.
"""
from __future__ import annotations

from nucleo import scheduler as S


def test_the_same_instant_answers_with_the_live_job():
    first = S.create("Recuérdale al operador: Dexter", "2026-10-30 09:00", name="aviso")
    again = S.create_unless_ringing("¡Hoy es el día! Dexter", "2026-10-30 09:00", "Dexter [worker:7]")
    assert again["ok"] and again["id"] == first["id"] and again.get("existed") is True
    assert len([j for j in S.list_jobs() if j["schedule"] == "2026-10-30 09:00"]) == 1


def test_another_instant_is_scheduled():
    S.create("x", "2026-10-30 09:00", name="aviso")
    other = S.create_unless_ringing("y", "2026-10-31 09:00", "y [worker:7]")
    assert other["ok"] and not other.get("existed")


def test_the_worker_door_uses_it():
    assert "scheduler.create_unless_ringing, what, spec, name" in open("nucleo/worker_api.py", encoding="utf-8").read()
