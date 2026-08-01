"""Observatory catalogue adapter for black-box voice scenarios."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tests.voice.e2e.agent.scenarios import SCENARIOS


def scenario_groups() -> list[dict[str, Any]]:
    cases = []
    for index, scenario in enumerate(SCENARIOS):
        raw = asdict(scenario)
        cases.append({
            "id": f"voice::scenario::{scenario.id}",
            "ordinal": index + 1,
            "title": scenario.id.replace("_", " "),
            "type": "conversation",
            "dimension": scenario.channel,
            "input": {"channel": scenario.channel, "goal": scenario.goal, "max_turns": scenario.turns},
            "expected": {"judge_checks": scenario.checks},
            "verification": "ejecutar el diálogo black-box y puntuar transcriptos, acciones y trazas con el juez",
            "execution_path": ["tester brain", scenario.channel, "LiveKit / data channel", "Zaelar agent",
                               "tools + frontend events", "transcript", "LLM judge + score"],
            "source": "tests/voice/e2e/agent/scenarios.py",
            "raw": raw,
            "execution": {
                "kind": "command",
                "argv": ["{python}", "-m", "tests.voice.e2e.agent.run", "--scenario", scenario.id,
                         "--no-open", "--hold", "0"],
                "nested_events": False,
                "requires_live": True,
            },
        })
    return [{
        "id": "scenarios", "label": "Escenarios de conversación + juez",
        "mode": "secuencial black-box · voz/chat/paste/websocket", "count": len(cases), "cases": cases,
        "execution": {
            "kind": "command",
            "argv": ["{python}", "-m", "tests.voice.e2e.agent.run", "--scenario", "all",
                     "--no-open", "--hold", "0"],
            "nested_events": False,
            "requires_live": True,
        },
    }]
