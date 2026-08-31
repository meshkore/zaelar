"""Tests for nucleo/flash/procs.py (V2-004 · T63) — thin bridge to the backed widget supervisor."""
from nucleo.flash import procs


def test_dispatch_delegates_to_supervisor(monkeypatch):
    calls = []
    import widgets.supervisor as sup
    monkeypatch.setattr(sup, "enqueue", lambda wid, a, p: calls.append((wid, a, p)) or True)
    assert procs.dispatch("navegador", "browse", {"url": "x"}) is True
    assert calls == [("navegador", "browse", {"url": "x"})]


def test_dispatch_false_when_not_backed(monkeypatch):
    import widgets.supervisor as sup
    monkeypatch.setattr(sup, "enqueue", lambda wid, a, p: False)
    assert procs.dispatch("clock", "tick", {}) is False


def test_status_and_running(monkeypatch):
    import widgets.supervisor as sup
    monkeypatch.setattr(sup, "info", lambda wid: {"backed": True, "running": True, "disabled": False, "fails": 0})
    monkeypatch.setattr(sup, "running", lambda: ["navegador"])
    assert procs.status("navegador")["running"] is True
    assert procs.running() == ["navegador"]


def test_is_backed_failsafe(monkeypatch):
    import widgets.supervisor as sup
    def boom(wid):
        raise RuntimeError("x")
    monkeypatch.setattr(sup, "is_backed", boom)
    assert procs.is_backed("navegador") is False    # never raises
