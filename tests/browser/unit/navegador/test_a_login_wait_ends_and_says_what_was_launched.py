"""A login wait has an end, and the browser says what it launched, not what it wanted (V2-835 T5).

Measured on a machine with no screen: the headed launch fell back to headless in silence while the log said «real
window»; he was told «I opened the login, sign in», said no, cancelled — and 13 minutes later the watcher, which had
no end but a sign-in, reminded him it was still waiting. Four things now hold:

  · the launch label is what was launched (`owner._headed`), and a sign-in whose headed launch fell back BLOCKS like
    «nowhere» instead of asking him to use a window that does not exist;
  · an ENDED task (cancelled, closed, failed) waits for nobody: `set_status` clears `awaiting_login`, and the watcher
    gives the window back and resumes the OTHER paused tasks — never the one that needed the login;
  · the watcher's life is bounded: after `_LOGIN_TIMEOUT` with no sign-in the task ends and the window closes;
  · «without the daemon I cannot continue» is said once per run; later blocks live in the processes panel.

Disarm: the ended-state flag clear removed / the timeout branch removed / the label read from `_headless()` / the
once-flag ignored → each red.
"""
import asyncio

import pytest

from nucleo import browser_window
from widgets.navegador import owner, tasks
from widgets.navegador.owner_login import _block_for_no_window as _block


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    saved = dict(tasks._tasks)
    tasks._tasks.clear()
    owner._auth_resume.clear()
    owner._login_timeouts.clear()
    browser_window.daemon_gone()
    told: list = []

    async def _notify(title, text, **kw):
        told.append(text)
        return True
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)
    stops: list = []

    async def _stop():
        stops.append(1)
    monkeypatch.setattr(owner, "stop", _stop)
    resumed: list = []

    async def _automate(goal, plan="", tid=""):
        resumed.append(tid)
    monkeypatch.setattr(owner, "_automate", _automate)
    monkeypatch.setattr(owner, "_LOGIN_POLL", 0.001)
    monkeypatch.setattr(owner, "_daemon_told", False)
    monkeypatch.setattr(owner, "_visible_override", True)
    yield {"told": told, "stops": stops, "resumed": resumed}
    owner._auth_resume.clear()
    owner._login_timeouts.clear()
    owner._task_browsers.clear()
    tasks._tasks.clear()
    tasks._tasks.update(saved)


class _Tab:
    async def _capture(self):
        return None


def _waiting(monkeypatch, logged_in=False):
    async def _is(tid, tb, site):
        return logged_in
    monkeypatch.setattr(owner, "_is_logged_in", _is)
    tid = tasks.create("buscar coches en una web con cuenta", title="Coches")
    other = tasks.create("buscar motos", title="Motos")
    owner._auth_resume.update({tid: {"goal": "buscar coches", "site": "x.com"},
                               other: {"goal": "buscar motos", "site": "x.com"}})
    tasks.set_status(tid, "needs_input")
    tasks.set_login_wait(tid, True)
    owner._task_browsers[tid] = _Tab()
    return tid, other


async def _run_watch(tid, during=None):
    w = asyncio.create_task(owner._login_watch(tid, "x.com"))
    owner._login_timeouts[tid] = w
    await asyncio.sleep(0.01)
    if during:
        during()
    await asyncio.wait_for(w, 2)


def test_cancelling_the_task_ends_the_watcher_and_gives_the_window_back(monkeypatch, _clean):
    tid, other = _waiting(monkeypatch)
    asyncio.run(_run_watch(tid, during=lambda: tasks.cancel(tid)))
    assert not tasks.get(tid)["awaiting_login"], "a cancelled task waits for nobody"
    assert _clean["stops"] and owner._visible_override is False, "the visible window is closed, back to headless"
    assert _clean["resumed"] == [other], "the OTHER paused task resumes; the cancelled one does not"
    assert not _clean["told"], "no reminder after he stopped waiting"


def test_the_wait_has_a_bounded_life(monkeypatch, _clean):
    monkeypatch.setattr(owner, "_LOGIN_TIMEOUT", 0.02)
    tid, other = _waiting(monkeypatch)
    asyncio.run(_run_watch(tid))
    t = tasks.get(tid)
    assert t["status"] == "failed" and not t["awaiting_login"]
    assert _clean["stops"] and _clean["resumed"] == [other], "the login task is not walked back into its wall"


def test_any_ended_state_clears_the_login_wait():
    tid = tasks.create("x", title="x")
    tasks.set_login_wait(tid, True)
    tasks.finish(tid, "done")
    assert not tasks.get(tid)["awaiting_login"]


def test_the_daemon_is_offered_once_per_run(_clean):
    a = tasks.create("a", title="a")
    b = tasks.create("b", title="b")
    asyncio.run(_block(a, "x.com"))
    asyncio.run(_block(b, "y.com"))
    assert len(_clean["told"]) == 1, _clean["told"]
    assert tasks.get(b)["blocked"] == "no_window", "the second block is still shown in the panel"
