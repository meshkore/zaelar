#
# test_work_agents.py — SlowBrain work agents + router + confirm-gate + return (V2-007).
# Verifies without starting real browsers/Claude:
#   - web.run orchestrates a browser task (creates a task, plans, queues `automate`) and does NOT deliver (the owner does so)
#   - web.run deduplicates refinements (similar_active) without creating another card
#   - code.run wraps the widget generator (create/modify) and the Architect
#   - the dispatcher routes by type (web/code/generic) and classifies unmarked requests
#   - the confirm-gate STOPS an irreversible action unless OK; without OK it does not execute the agent
#   - the return delivers only deliverable results by voice+UI+[SYSTEM] (not web)
# Run: .venv/bin/pytest tests/agent_headless/unit/agentes/test_work_agents.py
#
# ⚠️ V2-038: the one-shot agents in nucleo/agentes/ were PARKED (replaced by nucleo/workers/ — interactive
# sessions). dispatch.run_task/_deliver no longer exist. This test is SKIPPED (reversible; its coverage is taken over by
# tests/agent_headless/unit/workers/test_workers.py + the routing tests). Physical removal = team work.
import pytest
pytest.skip("nucleo/agentes one-shot parkeado en V2-038 (ver nucleo/workers/)", allow_module_level=True)

import asyncio

import pytest

from nucleo import dispatch
from nucleo.agentes import code as code_agent
from nucleo.agentes import web as web_agent
from nucleo.agentes.base import WorkResult


# ── web agent ────────────────────────────────────────────────────────────────────────────────────────────
def test_web_run_orchestrates_navegador(monkeypatch):
    from widgets.navegador import tasks as navtasks

    calls = {}
    monkeypatch.setattr(navtasks, "find_continuation", lambda goal: None)
    monkeypatch.setattr(navtasks, "create", lambda goal, title="": "task9")
    monkeypatch.setattr(navtasks, "inst_id", lambda tid: f"navegador::{tid}")
    monkeypatch.setattr(navtasks, "add_event", lambda tid, text: None)
    monkeypatch.setattr(navtasks, "finish", lambda *a, **k: None)
    # planner: does not start a real CodeAgent
    async def _fake_plan(goal, task):
        return "PLAN: ir a wallapop, filtrar por precio"
    monkeypatch.setattr(web_agent, "_plan", _fake_plan)

    async def _fake_brain_action(wid, action, payload):
        calls["brain_action"] = (wid, action, payload)
    import widgets.server_api as wsa
    monkeypatch.setattr(wsa, "brain_action", _fake_brain_action)

    task = dispatch.Task(id="t", request="En Wallapop busca una moto <5000€", kind="web")
    wr = asyncio.run(web_agent.run(task))
    assert wr.ok is True
    assert wr.deliver is False                     # el owner reporta el desenlace async
    assert calls["brain_action"][0] == "navegador"
    assert calls["brain_action"][1] == "automate"
    assert calls["brain_action"][2]["task_id"] == "task9"
    assert "PLAN" in calls["brain_action"][2]["plan"]


def test_web_run_refines_active_task(monkeypatch):
    """Clarification about a LIVE task → MODIFIES it (set_goal) on the same card, does NOT open another browser."""
    from widgets.navegador import tasks as navtasks
    created = {"n": 0}
    goals = {}
    monkeypatch.setattr(navtasks, "find_continuation", lambda goal: ("taskDUP", "working"))
    monkeypatch.setattr(navtasks, "inst_id", lambda tid: f"navegador::{tid}")
    monkeypatch.setattr(navtasks, "milestone", lambda tid, text: None)
    monkeypatch.setattr(navtasks, "set_goal", lambda tid, g: goals.__setitem__(tid, g))
    monkeypatch.setattr(navtasks, "create", lambda *a, **k: created.__setitem__("n", created["n"] + 1) or "x")

    task = dispatch.Task(id="t", request="no, de enduro 300 4T cerca de Soria", kind="web")
    wr = asyncio.run(web_agent.run(task))
    assert wr.ok is True and wr.deliver is False
    assert wr.meta.get("refined") is True
    assert created["n"] == 0                        # Did NOT create another card
    assert goals.get("taskDUP") == "no, de enduro 300 4T cerca de Soria"   # The clarification MODIFIED the goal


def test_web_run_reruns_finished_task(monkeypatch):
    """Clarification about a recently FINISHED task → RE-LAUNCHES the SAME card (same task_id), not a new one."""
    from widgets.navegador import tasks as navtasks
    created = {"n": 0}
    calls = {}
    monkeypatch.setattr(navtasks, "find_continuation", lambda goal: ("taskOLD", "done"))
    monkeypatch.setattr(navtasks, "inst_id", lambda tid: f"navegador::{tid}")
    monkeypatch.setattr(navtasks, "milestone", lambda tid, text: None)
    monkeypatch.setattr(navtasks, "set_goal", lambda tid, g: None)
    monkeypatch.setattr(navtasks, "create", lambda *a, **k: created.__setitem__("n", created["n"] + 1) or "x")

    async def _fake_plan(goal, task):
        return "PLAN"
    monkeypatch.setattr(web_agent, "_plan", _fake_plan)

    async def _fake_brain_action(wid, action, payload):
        calls["ba"] = payload
    import widgets.server_api as wsa
    monkeypatch.setattr(wsa, "brain_action", _fake_brain_action)

    task = dispatch.Task(id="t", request="en realidad quería de enduro, no eso", kind="web")
    wr = asyncio.run(web_agent.run(task))
    assert wr.ok is True and wr.meta.get("rerun") is True
    assert created["n"] == 0                        # Did NOT create another card
    assert calls["ba"]["task_id"] == "taskOLD"      # Relaunched on the SAME task/card


# ── code agent ───────────────────────────────────────────────────────────────────────────────────────────
def test_code_detectors():
    assert code_agent.is_widget_request("créame un widget del tiempo") is True
    assert code_agent.is_widget_request("arregla el bug de arranque") is False
    assert code_agent.is_architect_request("pregunta al architect del proyecto foo") is True


def test_code_run_creates_widget(monkeypatch):
    from widgets import generator
    monkeypatch.setattr(generator, "generate_widget", lambda spec, wid="", title="": {"ok": True, "id": "clima"})
    monkeypatch.setattr(code_agent, "_show", lambda wid: None)
    task = dispatch.Task(id="t", request="hazme un widget del clima", kind="code")
    wr = asyncio.run(code_agent.run(task))
    assert wr.ok is True and wr.deliver is True
    assert wr.meta.get("widget_id") == "clima"
    assert "clima" in wr.summary


def test_code_run_modifies_existing_widget(monkeypatch):
    from widgets import generator
    monkeypatch.setattr(code_agent, "_catalog_ids", lambda: ["agenda", "clock"])
    monkeypatch.setattr(code_agent, "_show", lambda wid: None)
    seen = {}
    def _mod(wid, change):
        seen["wid"], seen["change"] = wid, change
        return {"ok": True, "id": wid, "modified": True}
    monkeypatch.setattr(generator, "modify_widget", _mod)
    # Safety net: if routing mistakenly falls through to CREATE, do NOT start a real headless agent
    monkeypatch.setattr(generator, "generate_widget",
                        lambda *a, **k: pytest.fail("no debía crear, sino modificar"))
    task = dispatch.Task(id="t", request="modifica el widget agenda para añadir prioridad", kind="code")
    wr = asyncio.run(code_agent.run(task))
    assert wr.ok is True and seen["wid"] == "agenda"
    assert wr.meta.get("modified") is True


def test_code_run_architect(monkeypatch):
    from connectors.architect import service as architect
    seen = {}
    async def _ask(project, request):
        seen["project"], seen["request"] = project, request
    monkeypatch.setattr(architect, "ask", _ask)
    task = dispatch.Task(id="t", request="dile al architect del proyecto zaelar que revise el arranque", kind="code")
    wr = asyncio.run(code_agent.run(task))
    assert wr.ok is True and wr.deliver is False        # architect entrega su propio resultado
    assert seen["project"] == "zaelar"


# ── router + clasificación ───────────────────────────────────────────────────────────────────────────────
def test_router_sends_web_request_to_web_agent(monkeypatch):
    seen = {}
    async def _web_run(task):
        seen["task"] = task
        return WorkResult(ok=True, summary="en marcha", deliver=False)
    monkeypatch.setattr(web_agent, "run", _web_run)
    # Request without an explicit kind but clearly web-related → classified as 'web'
    task = dispatch.Task(id="t", request="en wallapop búscame una bici", kind="generic")
    wr = asyncio.run(dispatch.run_task(task))
    assert wr.deliver is False
    assert seen["task"].kind == "web"


# ── confirm-gate ─────────────────────────────────────────────────────────────────────────────────────────
def test_confirm_gate_blocks_irreversible(monkeypatch):
    ran = {"n": 0}
    async def _otros_run(task):
        ran["n"] += 1
        return WorkResult(ok=True, summary="hecho")
    from nucleo.agentes import otros as otros_agent
    monkeypatch.setattr(otros_agent, "run", _otros_run)

    task = dispatch.Task(id="t", request="borra la cuenta de correo", kind="generic")
    wr = asyncio.run(dispatch.run_task(task))
    assert wr.meta.get("needs_confirm") is True
    assert ran["n"] == 0                            # The agent was NOT executed without OK
    assert "?" in wr.summary                         # It is a confirmation question

    # With explicit OK, proceed
    task2 = dispatch.Task(id="t2", request="borra la cuenta de correo", kind="generic",
                          context={"confirmed": True})
    asyncio.run(dispatch.run_task(task2))
    assert ran["n"] == 1


# ── retorno (voz + UI + [SISTEMA]) ───────────────────────────────────────────────────────────────────────
def test_deliver_pushes_note_and_notifies(monkeypatch):
    pushed, notified = [], []
    import voice.brain_notes as bn
    import voice.proactive as pro
    monkeypatch.setattr(bn, "push", lambda text: pushed.append(text))
    async def _notify(title, text, **k):
        notified.append(text)
    monkeypatch.setattr(pro, "notify", _notify)

    task = dispatch.Task(id="t", request="calcula 2+2", kind="generic")
    asyncio.run(dispatch._deliver(WorkResult(ok=True, summary="son 4", deliver=True), task))
    assert any("son 4" in p for p in pushed)         # [SYSTEM] note
    assert notified == ["son 4"]                     # voice+UI

    # A web task (deliver=False) is NOT delivered here (its owner does so)
    pushed.clear(); notified.clear()
    asyncio.run(dispatch._deliver(WorkResult(ok=True, summary="en marcha", deliver=False), task))
    assert pushed == [] and notified == []
