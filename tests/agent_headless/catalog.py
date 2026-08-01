"""Rich Headless catalogue: routing corpus and conversational personas."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def search_groups() -> list[dict[str, Any]]:
    from tests.agent_headless.e2e.search.bot.cases import all_cases

    cases = []
    for index, raw in enumerate(all_cases()):
        cases.append({
            "id": f"agent-headless::search::{index:04d}",
            "ordinal": index + 1,
            "title": raw["input"],
            "type": "routing",
            "dimension": raw.get("scope", "search"),
            "input": {"operator": raw["input"]},
            "expected": {"route": raw.get("expect"), "answer_contains": raw.get("want", []),
                         "forbidden": raw.get("forbid", [])},
            "verification": "validar decisión FlashBrain; si busca, validar síntesis y respuesta",
            "execution_path": ["operator input", "FlashBrain function calling", "route decision",
                               "optional web_search", "answer synthesis", "route/content judge"],
            "source": "tests/agent_headless/e2e/search/bot/cases.py",
            "note": raw.get("note", ""),
            "raw": raw,
            "execution": {
                "kind": "command",
                "argv": ["{python}", "-m", "tests.agent_headless.e2e.search.bot.runner",
                         "--range", str(index), str(index + 1)],
                "nested_events": False,
                "requires_live": True,
            },
        })
    return [{
        "id": "search", "label": "Corpus de routing y búsqueda web", "mode": "orden acumulativo por tandas",
        "count": len(cases), "cases": cases,
        "execution": {"kind": "command",
                      "argv": ["{python}", "-m", "tests.agent_headless.e2e.search.bot.runner", "--next", "10"],
                      "nested_events": False, "requires_live": True, "batch_size": 10},
    }]


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
