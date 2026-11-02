"""Where no browser window can reach him, nothing offers him one; a wall is told, never handed to a login (V2-835 T5).

`reach()` was read by ONE caller — the last step of the sign-in — while three others offered the window on their own:
the voice catalogue (`allow_auth` was True on every turn), the wall note (it told the conversation to call
`authenticate_web` «so he solves the captcha»), and the browser agent's prompt («he will sign in by hand in a real
window»). So on a machine with no screen the agent offered, opened and kept reminding him of a window nobody could see.

The one answer is now read everywhere: the catalogue offers the tool only where `reach()` is non-empty; the wall note
names no login and, when a worker drives the tab, only informs (the worker owns the errand and picks another source);
the agent's prompts promise nothing about who signs in where.

Disarm: `allow_auth` back to a constant True / the old note → red.
"""
import pytest

from nucleo import browser_window
from nucleo.flash import router
from widgets.navegador import tasks


@pytest.fixture(autouse=True)
def _registry():
    saved = dict(tasks._tasks)
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()
    tasks._tasks.update(saved)


def _offered(monkeypatch, where: str) -> set:
    monkeypatch.setattr(browser_window, "reach", lambda: where)
    return {t["function"]["name"] for t in router.tools(router.tool_context())}


def test_the_catalogue_offers_the_login_tool_only_where_a_window_can_reach_him(monkeypatch):
    assert "authenticate_web" not in _offered(monkeypatch, "")
    assert "authenticate_web" in _offered(monkeypatch, browser_window.HERE)
    assert "authenticate_web" in _offered(monkeypatch, browser_window.DAEMON)


def _note(monkeypatch, *, worker: bool, url="https://www.coches.net/segunda-mano/") -> str:
    pushed: list = []
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "push", lambda text, *a, **k: pushed.append(text))
    from widgets.navegador.tasks import announce
    monkeypatch.setattr(announce, "_driven_by_worker", lambda tid: worker)
    tid = tasks.create("Busca un SUV de segunda mano por menos de 20.000 €")
    tasks._tasks[tid]["url"] = url
    tasks._announce_wall(tid, "el sitio nos ha bloqueado el acceso (respuesta 403)")
    return "\n".join(pushed)


@pytest.mark.parametrize("worker", [True, False])
def test_a_wall_note_never_sends_the_conversation_to_a_login(monkeypatch, worker):
    note = _note(monkeypatch, worker=worker)
    assert "BLOQUEÓ" in note and "403" in note, "the fact itself is lost"
    assert "authenticate_web" not in note and "que entre él" not in note


def test_a_worker_owns_its_wall_and_the_conversation_is_only_informed(monkeypatch):
    note = _note(monkeypatch, worker=True)
    assert "worker" in note and "EN ESTE TURNO" not in note
    own = _note(monkeypatch, worker=False)
    assert "EN ESTE TURNO" in own, "a tab nobody else drives is his to hear about now"


def test_the_browser_agent_promises_no_manual_sign_in():
    from widgets.navegador import agent
    for prompt in (agent._SYSTEM, agent._VISION_SYSTEM):
        assert "a mano" not in prompt and "ventana real" not in prompt.lower()
