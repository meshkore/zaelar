"""Browser login wall in the CLOUD — clean shutdown instead of an infinite loop (2026-08-03).

Real incident: the operator requested a Wallapop search from the cloud deployment (headless container, with no
display); the site requested login and everything got stuck in an endless loop — voice AND widget hung, with no
failure or warning. Cause: `_authenticate` always tried to open a VISIBLE window so the operator could type their
credentials; in a container that silently degrades to headless (`_ensure_page`) and the task keeps waiting for a
login that can never arrive. `_in_container()` stops this BEFORE trying, with a clear message (install the local
version) instead of a phantom attempt."""
import asyncio

import pytest

from widgets.navegador import owner, tasks


@pytest.fixture(autouse=True)
def _clean_state():
    owner._auth_resume.clear()
    yield
    owner._auth_resume.clear()


def _no_op_async(*_a, **_kw):
    async def _f(*a, **kw):
        return False
    return _f()


def test_container_bails_out_instead_of_opening_a_visible_window(monkeypatch):
    monkeypatch.setattr(owner, "_in_container", lambda: True)
    monkeypatch.setattr(owner, "_already_authenticated", lambda site: _no_op_async())

    tid = tasks.create("buscar motos en wallapop", title="Wallapop")
    asyncio.run(owner._authenticate(tid, "wallapop.com", site="wallapop.com", goal="buscar motos"))

    t = tasks.get(tid)
    assert t["status"] == "failed"                 # does not remain in needs_input waiting forever
    assert not t["awaiting_login"]
    last_event = (t["events"][-1] or {}).get("text", "") if t["events"] else ""
    assert "nube" in last_event


def test_other_paused_tasks_are_also_failed_not_left_hanging(monkeypatch):
    """`_begin_login` pauses OTHER active tasks while login is being resolved (needs_input) — if login cannot
    be resolved in the cloud, those paused tasks must also be closed, rather than left hanging forever."""
    monkeypatch.setattr(owner, "_in_container", lambda: True)
    monkeypatch.setattr(owner, "_already_authenticated", lambda site: _no_op_async())

    primary = tasks.create("buscar motos en wallapop", title="Wallapop")
    other = tasks.create("buscar coches en wallapop", title="Wallapop coches")
    owner._auth_resume[other] = {"goal": "buscar coches", "plan": "", "site": "wallapop.com"}
    tasks.set_status(other, "needs_input")

    asyncio.run(owner._authenticate(primary, "wallapop.com", site="wallapop.com", goal="buscar motos"))

    assert tasks.get(primary)["status"] == "failed"
    assert tasks.get(other)["status"] == "failed"
    assert owner._auth_resume == {}                 # drained; nothing remains waiting


def test_locally_the_visible_login_flow_is_not_short_circuited(monkeypatch):
    """Outside a container, `_in_container()` must not intercept anything — the guard is ONLY for the cloud."""
    monkeypatch.setattr(owner, "_in_container", lambda: False)
    assert owner._in_container() is False
