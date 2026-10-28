"""A network agent's rows never open a results sheet for an errand that delivers a DOCUMENT (node 2.553).

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es). The car REPORT's worker asked the network about city
electric cars, got a shopping agent, and `mesh_cli serve` pushed its eight rows onto a results sheet for the report:
«RENAULT 4 E-TECH 100% ELÉCTRICO… — 35.19» (a scale model), two charging cables, a wall poster, a remote-control car.
Every later prompt carried a sheet titled «Informe sobre coches eléctricos urbanos» full of toys beside the real
report, and asked how the report was going the turn said «del informe no me consta ningún dato todavía».

The worker still reads the agent's answer on stdout; only the automatic push is refused, at the bridge, and only for
a document errand (`nucleo/network_rows_gate.py`).
"""
from __future__ import annotations

import inspect
import json
import types

from nucleo import network_rows_gate as G
from nucleo.cli import mesh as mesh_cli, worker_api

TOYS = {"results": [{"title": "RENAULT 4 E-TECH 100% ELÉCTRICO 2025 GRIS escala 1:43", "price": "35.19"},
                    {"title": "Cable de carga eléctrico coche Toyota Urban Cruiser", "price": "229.22"}]}


def _push(monkeypatch, capsys) -> dict:
    sent = []
    monkeypatch.setenv("ZAELAR_TASK_ID", "5")
    from nucleo import mesh_agents
    from nucleo.cli import widget as widget_cli
    monkeypatch.setattr(mesh_agents, "serve", lambda *a, **k: {"ok": True, "agent": "ebay-finder", "data": TOYS})
    monkeypatch.setattr(widget_cli, "_act", lambda action, payload: sent.append(payload) or {"ok": True})
    mesh_cli.main(["serve", "coches eléctricos para ciudad"])
    assert json.loads(capsys.readouterr().out)["data"], "the worker still gets the agent's answer"
    assert sent, "the push itself still happens: the BRIDGE decides"
    return {"widget_id": sent[0]["widget_id"], "action": sent[0]["action"], "payload": dict(sent[0]["payload"])}


def test_the_push_onto_a_report_errand_is_refused(monkeypatch, capsys):
    payload = _push(monkeypatch, capsys)
    why = G.refused(types.SimpleNamespace(task_id="5", surface="informe"), "widget_data", payload)
    assert "document" in why


def test_the_push_onto_a_list_errand_goes_through_without_the_mark(monkeypatch, capsys):
    payload = _push(monkeypatch, capsys)
    assert G.refused(types.SimpleNamespace(task_id="3", surface="lista"), "widget_data", payload) == ""
    assert G.MARK not in payload["payload"], "the mark never reaches the widget"
    assert [i["title"][:9] for i in payload["payload"]["items"]] == ["RENAULT 4", "Cable de "]


def test_the_workers_own_rows_on_a_report_are_not_this_gates_business():
    own = {"widget_id": "results", "action": "append", "payload": {"items": [{"title": "Dacia Spring"}]}}
    assert G.refused(types.SimpleNamespace(task_id="5", surface="informe"), "widget_data", own) == ""


def test_the_bridge_asks_the_gate_before_it_executes():
    src = inspect.getsource(worker_api.worker_act)
    assert "_net.refused(" in src and src.index("_net.refused(") < src.index("_exec_allow("), \
        "the gate must run before the action executes"
