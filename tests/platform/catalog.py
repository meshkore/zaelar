"""Normalized test map consumed by CLI, Observatory and coding agents.

Every suite is exposed as the same hierarchy::

    suite -> ordered steps -> ordered groups -> executable cases

Pytest nodes are adapted automatically. Rich E2E corpora can add groups through a
``catalog_provider`` declared on their step in ``suite.json``. The UI therefore
does not know what a memory, voice or headless case is.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
from pathlib import Path
from typing import Any, Callable

from tests.run_testmap import DOMAINS


@dataclass(frozen=True)
class Suite:
    id: str
    label: str
    domain_ids: tuple[str, ...]
    description: str
    live_commands: tuple[tuple[str, ...], ...] = ()
    steps: tuple[dict, ...] = ()
    manifest: str = ""
    primary_case: str = ""
    case_count: int = 0


TESTS_ROOT = Path(__file__).resolve().parents[1]


def _load() -> dict[str, Suite]:
    suites: dict[str, Suite] = {}
    for path in sorted(TESTS_ROOT.glob("*/suite.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        suite = Suite(
            id=raw["id"], label=raw["label"], domain_ids=tuple(raw["domain_ids"]),
            description=raw["description"],
            live_commands=tuple(tuple(command) for command in raw.get("live_commands", ())),
            steps=tuple(raw.get("steps", ())), manifest=str(path.relative_to(TESTS_ROOT)),
            primary_case=str(raw.get("primary_case", "")),
            case_count=int(raw.get("case_count", 0)),
        )
        suites[suite.id] = suite
    return suites


SUITES = _load()


def deterministic_paths(suite_id: str) -> list[str]:
    wanted = {d for suite in SUITES.values() for d in suite.domain_ids} if suite_id == "all" else set(SUITES[suite_id].domain_ids)
    paths: list[str] = []
    for domain in DOMAINS:
        if domain["id"] not in wanted:
            continue
        for node in domain["nodes"]:
            if not node.get("live"):
                paths.extend(node.get("paths", ()))
    return list(dict.fromkeys(paths))


def suite_nodes(suite_id: str) -> list[dict]:
    """Return the canonical ordered steps for a suite, including their owned files."""
    wanted = set(SUITES[suite_id].domain_ids)
    return [node for domain in DOMAINS if domain["id"] in wanted for node in domain["nodes"]]


def suite_rows() -> list[dict[str, object]]:
    return [
        {"id": suite.id, "label": suite.label, "description": suite.description,
         "deterministic_files": len(deterministic_paths(suite.id)), "case_count": suite.case_count,
         "has_live": bool(suite.live_commands)}
        for suite in SUITES.values()
    ]


def _load_provider(reference: str) -> Callable[[], list[dict[str, Any]]]:
    module_name, separator, attribute = reference.partition(":")
    if not separator:
        raise ValueError(f"catalog_provider inválido: {reference!r}")
    provider = getattr(importlib.import_module(module_name), attribute)
    if not callable(provider):
        raise TypeError(f"catalog_provider no invocable: {reference!r}")
    return provider


def _search_blob(case: dict[str, Any]) -> str:
    return json.dumps(
        {key: value for key, value in case.items() if key not in {"raw", "search"}},
        ensure_ascii=False, default=str,
    ).lower()


def normalize_case(case: dict[str, Any], *, suite: str, step_id: str, group_id: str,
                   ordinal: int) -> dict[str, Any]:
    """Return one JSON-safe case following the platform-wide schema."""
    normalized = {
        "id": str(case["id"]),
        "suite": suite,
        "step_id": step_id,
        "group": group_id,
        "ordinal": int(case.get("ordinal", ordinal)),
        "title": str(case.get("title") or case["id"]),
        "type": str(case.get("type", "test")),
        "dimension": str(case.get("dimension", "")),
        "input": case.get("input", {}),
        "expected": case.get("expected", {}),
        "verification": str(case.get("verification", "finaliza correctamente")),
        "execution_path": list(case.get("execution_path", ())),
        "source": str(case.get("source", "")),
        "note": str(case.get("note", "")),
        "raw": case.get("raw", {}),
        "execution": dict(case.get("execution", {})),
    }
    # Force JSON safety at the contract boundary; providers may use dataclasses,
    # tuples or Paths internally.
    normalized = json.loads(json.dumps(normalized, ensure_ascii=False, default=str))
    normalized["search"] = _search_blob(normalized)
    return normalized


def _pytest_case(nodeid: str, *, suite: str, step_id: str, ordinal: int) -> dict[str, Any]:
    source, _, test_name = nodeid.partition("::")
    return normalize_case({
        "id": nodeid,
        "title": test_name or Path(source).name,
        "type": "pytest",
        "dimension": "deterministic",
        "input": {"nodeid": nodeid},
        "expected": {"status": "passed", "exit_code": 0},
        "verification": "pytest ejecuta fixtures, cuerpo del test y todas sus assertions",
        "execution_path": ["pytest collection", "fixture setup", "test call", "assertions", "fixture teardown"],
        "source": source,
        "raw": {"nodeid": nodeid},
        "execution": {"kind": "pytest", "nodeid": nodeid, "nested_events": True},
    }, suite=suite, step_id=step_id, group_id="pytest", ordinal=ordinal)


def owning_suite_label(nodeid: str) -> str:
    """Best-effort "which suite owns this pytest node" label for the aggregate 'all' run.

    Falls back to the raw tests/<dir> name (normalized to match a registered suite id, e.g.
    agent_headless -> agent-headless) when the directory isn't a formally registered suite
    (tests/platform's own self-tests, for instance) — still a useful bucket label even though
    it never appears in SUITES.
    """
    parts = nodeid.split("::", 1)[0].split("/")
    if len(parts) < 2 or parts[0] != "tests":
        return ""
    candidate = parts[1].replace("_", "-")
    return candidate if candidate in SUITES else parts[1]


def build_suite_catalog(suite_id: str, collected_tests: list[str]) -> dict[str, Any]:
    """Build the complete ordered map for one suite."""
    if suite_id == "all":
        return {
            "schema": 2, "suite": "all", "label": "Todos los tests", "steps": [],
            "tests": collected_tests, "count": len(collected_tests), "case_count": len(collected_tests),
            "test_suite": {test: owning_suite_label(test) for test in collected_tests},
            "manifest": "catálogo agregado", "ok": True,
        }
    suite = SUITES[suite_id]
    nodes = {node["id"]: node for node in suite_nodes(suite_id)}
    owned: set[str] = set()
    steps: list[dict[str, Any]] = []
    for order, declared in enumerate(suite.steps, start=1):
        node = nodes.get(declared["id"], {})
        paths = list(node.get("paths", ()))
        members = [test for test in collected_tests if test.split("::", 1)[0] in paths]
        owned.update(members)
        groups: list[dict[str, Any]] = []
        if members:
            groups.append({
                "id": "pytest", "label": "Tests deterministas", "mode": "pytest · orden de colección",
                "count": len(members),
                "target_id": f"{suite_id}::group::{declared['id']}::pytest",
                "execution": {"kind": "pytest", "nodeids": members, "nested_events": True},
                "cases": [_pytest_case(test, suite=suite_id, step_id=declared["id"], ordinal=index)
                          for index, test in enumerate(members, start=1)],
            })
        provider_ref = declared.get("catalog_provider")
        if provider_ref:
            for provided in _load_provider(str(provider_ref))():
                group_id = str(provided["id"])
                cases = [normalize_case(case, suite=suite_id, step_id=declared["id"], group_id=group_id,
                                        ordinal=index)
                         for index, case in enumerate(provided.get("cases", ()), start=1)]
                groups.append({**{key: value for key, value in provided.items() if key != "cases"},
                               "target_id": f"{suite_id}::group::{declared['id']}::{group_id}",
                               "count": len(cases), "cases": cases})
        steps.append({
            **declared,
            "order": order,
            "depends_on": list(declared.get("depends_on", ())),
            "channel": node.get("ch", declared.get("kind", "unit")),
            "paths": paths,
            "live": bool(node.get("live")),
            "command": node.get("cmd", ""),
            "nested_events": bool(node.get("nested_events")),
            "tests": members,
            "case_groups": groups,
            "case_count": sum(group["count"] for group in groups),
        })
    # A test not owned by a declared step is visible as a mapping defect instead
    # of silently disappearing from the Observatory.
    unmapped = [test for test in collected_tests if test not in owned]
    if unmapped:
        steps.append({
            "id": "unmapped", "label": "Sin mapear", "kind": "diagnostic", "order": len(steps) + 1,
            "channel": "pytest", "paths": [], "live": False, "command": "", "tests": unmapped,
            "case_groups": [{"id": "pytest", "label": "Tests sin paso declarado", "mode": "mapping gap",
                             "target_id": f"{suite_id}::group::unmapped::pytest",
                             "execution": {"kind": "pytest", "nodeids": unmapped, "nested_events": True},
                             "count": len(unmapped),
                             "cases": [_pytest_case(test, suite=suite_id, step_id="unmapped", ordinal=index)
                                       for index, test in enumerate(unmapped, start=1)]}],
            "case_count": len(unmapped),
        })
    case_count = sum(step["case_count"] for step in steps)
    return {
        "schema": 2, "suite": suite_id, "label": suite.label, "description": suite.description,
        "requirements": list(json.loads((TESTS_ROOT / suite.manifest).read_text())["requirements"]),
        "execution_policy": {"order": ["step.order", "group order", "case.ordinal"],
                             "stop_on_failure": False, "results": "events.jsonl"},
        "steps": steps, "tests": collected_tests, "count": len(collected_tests), "case_count": case_count,
        "manifest": suite.manifest, "ok": True,
    }


def find_case(catalog: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    for step in catalog.get("steps", ()):
        for group in step.get("case_groups", ()):
            if group.get("target_id") == case_id and group.get("execution"):
                return normalize_case({
                    "id": case_id,
                    "title": group.get("label", case_id),
                    "type": "group",
                    "dimension": group.get("mode", "ordered"),
                    "input": {"cases": group.get("count", 0), "order": "catalog"},
                    "expected": {"status": "passed"},
                    "verification": "ejecutar todos los casos del grupo en el orden declarado",
                    "execution_path": ["catalog order", "case execution", "event stream", "aggregate score"],
                    "execution": group["execution"],
                }, suite=catalog["suite"], step_id=step["id"], group_id=group["id"], ordinal=1)
            for case in group.get("cases", ()):
                if case.get("id") == case_id:
                    return case
    return None
