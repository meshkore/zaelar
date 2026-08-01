"""Tests de widgets/refs.py (resolución de referencias a items) + fechas/horas de agenda (V2-026)."""
from widgets import refs


def test_id_field_from_manifest():
    # el campo id de cada acción se deduce del payload declarado en el manifest real de la agenda
    assert refs.id_field_for_action("agenda", "done") == "taskId"
    assert refs.id_field_for_action("agenda", "drop_project") == "projectId"
    assert refs.id_field_for_action("agenda", "add_meeting") is None   # crea un item → no resuelve


def test_resolve_task_by_natural_language():
    r = refs.resolve("agenda", "done", "la tarea del daemon")
    assert r.ok and r.payload["taskId"] == "t_daemon"
    r2 = refs.resolve("agenda", "snooze", "lo de Reddit")
    assert r2.ok and r2.payload["taskId"] == "t_reddit"


def test_resolve_project_not_samename_task():
    # "CryptoKnight" es a la vez un proyecto y una tarea ("Revisión de CryptoKnight"); drop_project→projectId
    # debe apuntar al PROYECTO, no a la tarea (el filtro por `field` lo garantiza).
    r = refs.resolve("agenda", "drop_project", "el proyecto CryptoKnight")
    assert r.ok and r.payload["projectId"] == "cryptoknight"


def test_add_meeting_needs_no_ref():
    r = refs.resolve("agenda", "add_meeting", "")
    assert r.ok                                     # no hay item que resolver


def test_no_match_asks_not_invents():
    r = refs.resolve("agenda", "done", "algo que no existe en absoluto zzz")
    assert not r.ok and r.needs in ("no_match", "ambiguous") and r.candidates


def test_respects_a_real_given_id():
    r = refs.resolve("agenda", "done", "", {"taskId": "t_daemon"})
    assert r.ok and r.payload["taskId"] == "t_daemon"


def test_items_line_lists_live_items():
    line = refs.items_line("agenda")
    assert "items ahora" in line and "daemon" in line.lower()


# ── fechas/horas del habla (agenda) ────────────────────────────────────────────────────────────────────────
def test_agenda_relative_dates_and_times():
    from widgets.agenda import data as a
    import time
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    assert a._resolve_date("mañana") == tomorrow
    assert a._resolve_date("hoy") == today
    assert a._resolve_date("2026-08-01") == "2026-08-01"
    assert a._resolve_date("") == today
    assert a._resolve_time("cinco") == "17:00"          # sin am/pm, 1–7 → tarde
    assert a._resolve_time("9 de la mañana") == "09:00"
    assert a._resolve_time("17:00") == "17:00"


def test_agenda_add_meeting_persists_normalized(tmp_path, monkeypatch):
    from widgets.agenda import data as a
    from widgets import store
    import time
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    before = len(a.load_db().get("meetings", []))
    a.apply_action("add_meeting", {"title": "TEST_ref dentista", "date": "mañana", "startTime": "cinco"})
    ms = a.load_db().get("meetings", [])
    assert len(ms) == before + 1
    m = ms[-1]
    assert m["date"] == tomorrow and m["startTime"] == "17:00" and m["title"] == "TEST_ref dentista"
    # limpieza: quita la cita de prueba
    db = store.load("agenda", {})
    db["meetings"] = [x for x in db.get("meetings", []) if x.get("title") != "TEST_ref dentista"]
    store.save("agenda", db)
