"""`hbmesh serve --agent <id>` asks THAT agent first — the shape every worker reached for (V2-831 A1).

`find` returns agents by id, and the worker then wants one of them: it wrote `hbmesh serve "…" --agent ybana` on
pass after pass (V2-776 K3, demo pass 1 B1 2026-10-29), and the bridge refused it with «no --agent». The natural
shape is now the declared one: `--agent` reorders the agents the network returned — never one it did not.

Disarm: drop the reorder in `mesh_agents.serve` → red.
"""
from __future__ import annotations

from nucleo import mesh_agents


def _serve(monkeypatch, agent_id):
    asked = []
    monkeypatch.setattr(mesh_agents, "find", lambda errand, **k: {"intent": "", "agents": [
        {"agent_id": "ebay-finder"}, {"agent_id": "ybana"}], "coverage": "full", "reached": True})
    monkeypatch.setattr(mesh_agents, "_failing_last", lambda agents: agents)
    monkeypatch.setattr(mesh_agents, "_ask_in_turn", lambda agents, *a, **k: asked.extend(agents) or {"ok": True})
    try:
        from nucleo import workflows
        monkeypatch.setattr(workflows, "plan", lambda errand: None)
    except Exception:  # noqa: BLE001
        pass
    mesh_agents.serve("sneakers size 42 under 80 euros", agent_id=agent_id)
    return [a["agent_id"] for a in asked]


def test_the_chosen_agent_is_asked_first(monkeypatch):
    assert _serve(monkeypatch, "ybana") == ["ybana", "ebay-finder"]


def test_an_agent_the_network_did_not_return_is_never_asked(monkeypatch):
    assert _serve(monkeypatch, "made-up-agent") == ["ebay-finder", "ybana"]


def test_the_cli_declares_the_flag():
    from nucleo.cli import mesh
    assert "--agent <agent_id>" in mesh._USAGE[1]
