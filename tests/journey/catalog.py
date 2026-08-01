"""Normalized Observatory provider for the chronological whole-system journey."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent


def load_plan() -> dict[str, Any]:
    return json.loads((HERE / "journey.json").read_text(encoding="utf-8"))


def case_id(index: int) -> str:
    return f"journey::whole-system-v1::{index:04d}"


def _path(case: dict[str, Any]) -> list[str]:
    channel = case["channel"]
    op = case["op"]
    routes = {
        "headless": ["operator utterance", "POST /api/flash/say", "FlashBrain + session window",
                     "tools/tags/worker dispatch", "memory ingestion", "observable reply"],
        "browser-api": ["browser/canvas intent", "widget or canvas HTTP API", "widget data owner",
                        "memory state + observer event", "subsequent FlashBrain context"],
        "observer": ["GET /api/tasks or /api/debug", "active-session registry + unified observer",
                     "causal correlation", "inline assertion"],
        "meshkore-http": ["HTTP control plane", "MeshKore manager", "WebSocket bridge state", "status assertion"],
        "meshkore": ["peer message", "security fence + relationship capsule", "cluster FlashBrain tier",
                     "identity/no-reintroduction assertions"],
        "http": [f"HTTP {op}", "live isolated engine", "JSON contract", "assertions"],
    }
    return routes.get(channel, [channel, op, "assertions"])


def serialize(index: int, case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case_id(index),
        "ordinal": index + 1,
        "title": f"{case['id']} · {case['title']}",
        "type": case["op"],
        "dimension": f"{case['phase']} · {case['channel']}",
        "input": {"channel": case["channel"], "operation": case["op"], "value": case.get("input"),
                  "consumes": case.get("consumes", [])},
        "expected": {**case.get("expected", {}), "produces": case.get("produces", [])},
        "verification": "ejecutar después de todos sus prerequisitos y validar respuesta, estado y efectos observables",
        "execution_path": _path(case),
        "source": "tests/journey/journey.json",
        "note": "Estado compartido dentro del run; un caso aislado reconstruye todo su prefijo causal.",
        "raw": case,
        "execution": {
            "kind": "command",
            "argv": ["{python}", "-m", "tests.journey.runner", "--target", str(index)],
            "nested_events": True,
            "stateful": True,
            "replay_prefix": True,
            "isolated_workspace": True
        }
    }


def platform_groups() -> list[dict[str, Any]]:
    plan = load_plan()
    cases = [serialize(index, case) for index, case in enumerate(plan["cases"])]
    return [{
        "id": plan["id"], "label": plan["label"],
        "mode": "engine y workspace aislados · una sesión · orden causal obligatorio",
        "description": plan["description"], "cases": cases,
        "execution": {
            "kind": "command", "argv": ["{python}", "-m", "tests.journey.runner", "--all"],
            "nested_events": True, "stateful": True, "isolated_workspace": True
        }
    }]
