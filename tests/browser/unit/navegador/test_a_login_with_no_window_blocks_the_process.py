"""A sign-in he must do where no browser window can reach him BLOCKS the process, and says why (V2-822).

The operator's decision 1 (2026-10-27): when a page needs him to authenticate, the process waits for him and watches
the browser it opened. Where that window can open is ONE question (`nucleo/browser_window.reach`): on a machine with a
display, here; with none (a container), only on his computer through a connected daemon that declares it can open a
browser; otherwise nowhere — and then the process is BLOCKED with that state (not failed, not waiting for a window
that cannot exist) and the agent tells him, in his language, that without the daemon it cannot continue.

Replaces the 2026-08-03 cloud bail-out, which FAILED the tasks with a Spanish sentence about «the local version».
Disarm: `reach()` answering `here` whatever the environment → red.
"""
import asyncio

import pytest

from nucleo import browser_window, sheets
from widgets.navegador import owner, tasks


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    owner._auth_resume.clear()
    browser_window.daemon_gone()
    told: list = []

    async def _notify(title, text, **kw):
        told.append((text, kw.get("speak", True)))
        return True
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)

    async def _no_session(site):
        return False
    monkeypatch.setattr(owner, "_already_authenticated", _no_session)
    yield told
    owner._auth_resume.clear()
    browser_window.daemon_gone()


def _headless(monkeypatch):
    monkeypatch.setattr(browser_window, "_has_display", lambda: False)


def test_where_a_window_can_open_is_one_answer(monkeypatch):
    monkeypatch.setattr(browser_window, "_has_display", lambda: True)
    assert browser_window.reach() == browser_window.HERE
    _headless(monkeypatch)
    assert browser_window.reach() == "", "no display and no daemon: nowhere"
    browser_window.daemon_connected(["files.list", "files.read"], opener=lambda url, tid: True)
    assert browser_window.reach() == "", "a daemon that did not declare a browser cannot open one"
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda url, tid: True)
    assert browser_window.reach() == browser_window.DAEMON
    browser_window.daemon_gone()
    assert browser_window.reach() == ""


def test_no_window_blocks_the_process_and_tells_him_why(monkeypatch, _clean):
    _headless(monkeypatch)
    primary = tasks.create("buscar motos en wallapop", title="Wallapop")
    other = tasks.create("buscar coches en wallapop", title="Wallapop coches")
    owner._auth_resume[other] = {"goal": "buscar coches", "plan": "", "site": "wallapop.com"}
    tasks.set_status(other, "needs_input")

    asyncio.run(owner._authenticate(primary, "wallapop.com", site="wallapop.com", goal="buscar motos"))

    for tid in (primary, other):
        t = tasks.get(tid)
        assert t["status"] == "needs_input" and t["blocked"] == "no_window", f"blocked, not failed: {t['status']}"
        assert not t["awaiting_login"] and not t.get("question"), "no window is waited for, no question is open"
    rec = type("R", (), {"nav_task": primary, "task_id": "w1"})()
    assert sheets.browser_for([rec])["blocked"] == "no_window", "the process record carries the state the panel paints"
    said = owner._say().login_needs_daemon
    assert said and _clean == [(said.replace("{site}", "wallapop.com"), True)], \
        f"told once, in his language, by voice and in the chat: {_clean}"


def test_a_connected_daemon_opens_the_window_on_his_computer(monkeypatch, _clean):
    _headless(monkeypatch)
    opened: list = []
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda url, tid: opened.append(url))
    tid = tasks.create("buscar motos en wallapop", title="Wallapop")
    asyncio.run(owner._authenticate(tid, "https://es.wallapop.com/login", site="wallapop.com", goal="buscar motos"))
    t = tasks.get(tid)
    assert opened == ["https://es.wallapop.com/login"], opened
    assert t["awaiting_login"] and not t.get("blocked"), "the process waits for him, it is not blocked"
