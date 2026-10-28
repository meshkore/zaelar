"""The grace turns must SEE the browser worker, or every round is a race again.

Measured on `search-buy-guitar__es` round 22 (2026-08-24): the worker was alive at the turn cap, the sheet
was filling up, and the grace block printed nothing — not in this round, not in ANY recorded round. The
predicate `navegador_task_is_live()` matched `kind == "navegador"`, but `/api/tasks` is the WORKER-session
registry (`dispatch.active_sessions()`), and a browser errand's session kind there is `"web"` — "navegador"
is the widget's id one layer down. A predicate that can never match does not fail: it quietly turns the
grace block into dead code, and the harness goes back to ending every round as a budget-vs-browser race —
the exact confound the grace block was built to remove (measured 2026-08-20, `hotel-under-15-days`: the
result arrived 16 s after the last turn and the round scored the clock, not the product).
"""
from tests.use_cases.e2e.agent import probe_client, verify


def _with_tasks(monkeypatch, tasks):
    monkeypatch.setattr(probe_client, "live_tasks", lambda: tasks)


def test_a_live_WEB_worker_session_is_seen(monkeypatch):
    """The value production actually emits: kind='web', status='running'."""
    _with_tasks(monkeypatch, [{"id": "1", "kind": "web", "status": "running", "goal": "busca una guitarra"}])
    assert verify.navegador_task_is_live() is True


def test_queued_counts_too(monkeypatch):
    _with_tasks(monkeypatch, [{"id": "1", "kind": "web", "status": "queued"}])
    assert verify.navegador_task_is_live() is True


def test_a_finished_or_absent_task_does_not_grant_grace(monkeypatch):
    """Sensitivity the other way: grace on a guess stretches every round (the predicate's own docstring)."""
    _with_tasks(monkeypatch, [])
    assert verify.navegador_task_is_live() is False
    _with_tasks(monkeypatch, [{"id": "1", "kind": "web", "status": "done"}])
    assert verify.navegador_task_is_live() is False


def test_a_non_web_worker_is_not_a_browser(monkeypatch):
    """A code/memory worker finishing late is not a browser result in flight."""
    _with_tasks(monkeypatch, [{"id": "1", "kind": "code", "status": "running"}])
    assert verify.navegador_task_is_live() is False


def test_an_unreadable_engine_reads_as_not_live(monkeypatch):
    def _boom():
        raise RuntimeError("down")
    monkeypatch.setattr(probe_client, "live_tasks", _boom)
    assert verify.navegador_task_is_live() is False
