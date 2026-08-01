"""Normalized, JSON-safe catalogue for every memory-bot request.

The executable Python corpora remain the source of truth. This adapter exposes their
complete inputs and expectations to the Test Observatory without maintaining a second
hand-written list.
"""
from __future__ import annotations

from collections import Counter
import importlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
_INPUT_KEYS = {
    "text", "texts", "q", "op", "hb", "say", "inbound", "outbound", "save",
    "set", "seed", "noise", "distractors", "needles", "set_state", "bg_slots",
}
_META_KEYS = {"t", "dim", "note"}


def case_id(corpus: str, index: int) -> str:
    return f"memory::{corpus}::{index:04d}"


def _input(case: dict[str, Any]) -> dict[str, Any]:
    return {key: case[key] for key in case if key in _INPUT_KEYS}


def _expected(case: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items()
            if key not in _INPUT_KEYS and key not in _META_KEYS}


def _title(case: dict[str, Any]) -> str:
    value: Any = (case.get("q") or case.get("text") or case.get("op") or case.get("say")
                  or case.get("inbound") or case.get("outbound") or case.get("summary"))
    if not value and case.get("texts"):
        value = case["texts"][0]
    if not value:
        value = case.get("note") or case.get("t") or "memory case"
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return value[:240]


def _verification(case: dict[str, Any]) -> str:
    kind = case.get("t", "unknown")
    if kind == "save":
        layers = case.get("in") or case.get("any") or []
        target = "DESCARTE" if not layers else " / ".join(layers)
        state = f"; state.{case['state_key']} poblado" if case.get("state_key") else ""
        return f"ingerir por CORAZÓN; marker={case.get('marker')!r}; destino={target}{state}"
    if kind == "extract":
        return ("ingerir UN turno conversacional por el CORAZÓN real; validar número de píldoras, descartes, "
                f"state={case.get('state', {})}, slots={case.get('slots', {})}, contenido={case.get('contains', [])}")
    if kind == "query":
        return (f"componer vista FlashBrain vía {case.get('via', 'long')}; debe contener "
                f"{case.get('want', [])}; no debe contener {case.get('not_want', [])}")
    if kind == "turn":
        return f"registrar turno en recencia; durable esperado={case.get('durable', 'no graduado')}"
    if kind == "connector":
        return (f"ingestar fuente={case.get('platform')} sender={case.get('sender') or case.get('entity')}; "
                f"trust={case.get('trust', 'external')}; capas={case.get('in', ['short'])}")
    if kind in {"forget", "unforget"}:
        return f"ruta NL {kind}; marker={case.get('marker')!r}; hard={bool(case.get('hard'))}"
    if kind == "dedup":
        return f"colapsar {len(case.get('texts', []))} fraseos en ≤{case.get('max_count', 1)} recuerdo(s)"
    if kind in {"source_query", "recall_probe"}:
        return f"consultar {case.get('source') or case.get('platform') or case.get('via')}; want={case.get('want', [])}"
    if kind == "scale":
        return (f"sembrar ruido={case.get('noise')} + needles={len(case.get('needles', []))}; "
                f"latencia máxima={case.get('max_ms')}ms")
    return f"ejecutar operación {kind}; validar {json.dumps(_expected(case), ensure_ascii=False, default=str)}"


def _execution_path(case: dict[str, Any]) -> list[str]:
    """Human-readable map of the production path exercised by a corpus case."""
    kind = case.get("t", "unknown")
    routes = {
        "save": ["nucleo.memory_agent.ingest_utterance", "memory.queue", "memory.writer", "SQLite + embeddings",
                 "state / recent_short / semantic query probes"],
        "extract": ["turno natural del operador", "nucleo.memory_agent.ingest_utterance",
                    "nucleo.mem_processor (CORAZÓN LLM)", "gates deterministas de precisión/secretos/corrección",
                    "píldoras canónicas + slots + state + concepts", "memory.queue/writer/SQLite",
                    "assertions multi-hecho + evidencia completa"],
        "query": ["nucleo.flash.memory_cache._compose", "nucleo.flash.prompt.needs_recall",
                  "nucleo.flash.prompt.compose_recall", "memory retriever + reranker", "FlashBrain prompt view"],
        "turn": ["operator utterance", "memory_agent ingest", "conversation short buffer", "durable-layer probes"],
        "connector": ["memory.ingest_message", "source/entity index", "memory.queue", "SQLite + embeddings",
                      "recent_by_source + trust/durability checks"],
        "source_query": ["source/entity lookup", "memory.recent_by_source", "content and provenance assertion"],
        "recall_probe": ["memory_agent ingestion", "semantic recall", "retriever result assertion"],
        "scale": ["isolated temporary database", "bulk seed", "FTS/vector retrieval", "needle assertions",
                  "p50/max latency score"],
        "dedup": ["multiple memory_agent ingests", "writer semantic dedup", "durable-row count + weight assertion"],
        "forget": ["natural-language forget route", "memory invalidation", "state/short/long absence probes"],
        "unforget": ["natural-language restore route", "memory revalidation", "layer recovery probes"],
        "episode": ["episodic write", "episode index", "temporal/content recall assertion"],
        "ui_state": ["memory.set_state", "state persistence", "memory_cache._compose", "FlashBrain visibility assertion"],
        "compose_check": ["state patch", "background-slot seed", "memory.compose_state", "prompt block assertions"],
        "worker_write": ["memory_agent.remember_external", "external-write gates", "writer/DB", "source + layer probes"],
        "cluster_exchange": ["cluster inbound/outbound framing", "trust gate", "memory ingestion", "recall assertion"],
        "consolidate": ["memory.consolidate", "dedup/decay/slot healing", "durable state assertion"],
        "heal_slots": ["pathological slot seed", "memory.consolidate", "heal_slots", "single-current-value assertion"],
        "slot_count": ["canonical slot resolution", "SQLite valid-row query", "cardinality/current-value assertion"],
        "weight_check": ["memory write/reinforcement", "SQLite weight read", "threshold assertion"],
    }
    return routes.get(kind, [f"memory corpus dispatcher ({kind})", "production memory API", "declared assertion"])


def serialize_case(corpus: str, index: int, case: dict[str, Any]) -> dict[str, Any]:
    raw = json.loads(json.dumps(case, ensure_ascii=False, default=str))
    entry = {
        "id": case_id(corpus, index),
        "corpus": corpus,
        "index": index,
        "ordinal": index + 1,
        "type": case.get("t", "unknown"),
        "dimension": case.get("dim", ""),
        "title": _title(case),
        "input": _input(raw),
        "expected": _expected(raw),
        "verification": _verification(raw),
        "execution_path": _execution_path(raw),
        "note": case.get("note", ""),
        "raw": raw,
        "source": f"tests/memory/e2e/bot/{'cases.py' if corpus == 'v1' else f'cases{corpus[1:]}.py'}",
        "execution": {
            "kind": "command",
            "argv": ["{python}", "-m", "tests.memory.e2e.bot.runner", "--corpus", corpus,
                     *( ["--fresh", "--range", "0", str(index + 1)] if corpus == "v4"
                        else ["--range", str(index), str(index + 1)] )],
            "nested_events": True,
            "stateful": True,
            "replay_prefix": corpus == "v4",
        },
    }
    # Precompute the search haystack once on the server. The dashboard can then
    # filter almost two thousand cases without serialising every object per keypress.
    entry["search"] = json.dumps(
        {key: value for key, value in entry.items() if key != "raw"},
        ensure_ascii=False,
        default=str,
    ).lower()
    return entry


def build_catalog() -> dict[str, Any]:
    manifest = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))
    groups = []
    total = 0
    for declared in manifest["corpora"]:
        module = importlib.import_module(f"{__package__}.{declared['module']}")
        cases = [serialize_case(declared["id"], index, case) for index, case in enumerate(module.CASES)]
        counts = Counter(case["type"] for case in cases)
        groups.append({**declared, "count": len(cases), "types": dict(sorted(counts.items())), "cases": cases})
        total += len(cases)
    return {**manifest, "total": total, "groups": groups}


def platform_groups() -> list[dict[str, Any]]:
    """Rich corpus provider for the platform-wide catalogue contract."""
    catalog = build_catalog()
    groups = []
    for group in catalog["groups"]:
        full_dialogue = group["id"] == "v4"
        groups.append({
            **group,
            "execution": {
                "kind": "command",
                "argv": ["{python}", "-m", "tests.memory.e2e.bot.runner", "--corpus", group["id"],
                         *(["--fresh", "--range", "0", str(group["count"])] if full_dialogue
                           else ["--next", "10"])],
                "nested_events": True,
                "stateful": True,
                "batch_size": group["count"] if full_dialogue else 10,
            },
        })
    from tests.memory.e2e.timeline.cases import platform_group
    # The focused conversational gateway is the primary active-memory test. The
    # deterministic chronology follows it; historical corpora remain below.
    dialogue = [group for group in groups if group["id"] == "v4"]
    historical = [group for group in groups if group["id"] != "v4"]
    return [*dialogue, platform_group(), *historical]
