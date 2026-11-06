"""Rich Headless catalogue: the conversational personas (a live bench, by request)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def persona_groups() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parent / "harness" / "personas"
    cases = []
    for index, path in enumerate(sorted(root.glob("*.md"))):
        persona = path.stem
        prompt = path.read_text(encoding="utf-8")
        cases.append({
            "id": f"agent-headless::persona::{persona}",
            "ordinal": index + 1,
            "title": persona.replace("_", " "),
            "type": "synthetic-dialogue",
            "dimension": "persona",
            "input": {"persona": persona, "prompt": prompt},
            "expected": {"judge_dimensions": ["naturalness", "reasoning", "helpfulness", "persona", "honesty",
                                                    "responsiveness", "memory", "name"]},
            "verification": "conversación multi-turno y evaluación separada de calidad por juez",
            "execution_path": ["persona simulator", "multi-turn dialogue", "Zaelar LLM", "transcript",
                               "quality judge", "dimension scores"],
            "source": str(path.relative_to(Path(__file__).resolve().parents[2])),
            "raw": {"persona": persona, "prompt": prompt},
            "execution": {"kind": "command",
                          "argv": ["{python}", "-m", "tests.agent_headless.harness.run", persona],
                          "nested_events": False, "requires_live": True},
        })
    return [{
        "id": "personas", "label": "Personas sintéticas + juez", "mode": "conversación multi-turno",
        "count": len(cases), "cases": cases,
        "execution": {"kind": "command", "argv": ["{python}", "-m", "tests.agent_headless.harness.run"],
                      "nested_events": False, "requires_live": True},
    }]
