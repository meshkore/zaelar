"""What he says to a widget build WHILE it runs is applied to the widget once it exists (node 2.556).

three-tasks-at-once (2026-10-11 11:34, ES and EN). The platform game was a one-shot `generate_widget` call of up to
eight minutes; «make the jump higher» and «add coins» were sent to it with `send_to_worker`, the session queued them,
and `GeneratorBackend.send` was a bare `return`. The game came out with neither, while the replies said the changes
had been passed on. Now every message that arrived during the build becomes ONE `modify_widget` pass on the widget
just created, and the result summary says whether it landed.
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.workers.providers import generator as gs

GAME = "Crear un widget nuevo: un juego de plataformas tipo Super Mario, jugable con teclado"


def _results(b) -> list[dict]:
    out = []
    while not b._q.empty():
        ev = b._q.get_nowait()
        if ev.type in ("result", "phase"):
            out.append({"type": ev.type, **ev.data})
    return out


@pytest.fixture
def build(monkeypatch):
    from nucleo.agentes import code as _code
    from widgets import generator
    calls = {"modify": []}
    b = gs.GeneratorBackend()
    b._task_id = "6"

    def _generate(*a, **k):
        # he speaks while the one-shot call runs: the session's inject reaches the backend's `send`
        asyncio.run(b.send("El operador pide que el salto sea más alto y flotante"))
        asyncio.run(b.send("Y que haya monedas para ir cogiendo"))
        return {"ok": True, "id": "juego-plataformas-tipo"}

    monkeypatch.setattr(generator, "generate_widget", _generate)
    monkeypatch.setattr(generator, "modify_widget",
                        lambda wid, change, token="": calls["modify"].append((wid, change)) or {"ok": True, "id": wid})
    monkeypatch.setattr(_code, "widget_action", lambda req: ("create", ""))
    return b, calls


def test_both_messages_reach_the_widget_in_one_modify_pass(build):
    b, calls = build
    asyncio.run(b._drive(GAME))
    assert len(calls["modify"]) == 1, calls
    wid, change = calls["modify"][0]
    assert wid == "juego-plataformas-tipo"
    assert "salto sea más alto" in change and "monedas" in change
    result = [r for r in _results(b) if r["type"] == "result"][0]
    assert result["ok"] and langs.current_language().widget_changes_applied in result["summary"], result


def test_a_modify_that_fails_is_said_and_the_widget_stands(build, monkeypatch):
    b, calls = build
    from widgets import generator
    monkeypatch.setattr(generator, "modify_widget", lambda *a, **k: {"ok": False, "error": "did not validate"})
    asyncio.run(b._drive(GAME))
    result = [r for r in _results(b) if r["type"] == "result"][0]
    assert result["ok"] and result["data"]["widget"] == "juego-plataformas-tipo"
    assert langs.current_language().widget_changes_not_applied in result["summary"], result


def test_a_build_nobody_spoke_to_is_not_modified(monkeypatch):
    from nucleo.agentes import code as _code
    from widgets import generator
    seen = []
    monkeypatch.setattr(generator, "generate_widget", lambda *a, **k: {"ok": True, "id": "w"})
    monkeypatch.setattr(generator, "modify_widget", lambda *a, **k: seen.append(a) or {"ok": True})
    monkeypatch.setattr(_code, "widget_action", lambda req: ("create", ""))
    b = gs.GeneratorBackend()
    asyncio.run(b._drive(GAME))
    assert seen == [] and _results(b)[-1]["summary"] == "He creado el widget «w»."
