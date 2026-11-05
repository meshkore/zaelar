from pathlib import Path

from tests.platform.catalog import SUITES, build_suite_catalog, deterministic_paths, find_case
from tests.memory.e2e.bot.catalog import build_catalog


ENGINE = Path(__file__).resolve().parents[3]


def test_every_catalogued_path_exists():
    missing = [path for path in deterministic_paths("all") if not (ENGINE / path).exists()]
    assert missing == []


def test_core_operator_suites_are_declared():
    assert {"use_cases", "memory", "agent-headless", "voice", "browser"}.issubset(SUITES)


def test_memory_request_catalog_is_complete_and_json_safe():
    import json

    catalog = build_catalog()
    assert catalog["total"] == 1865
    assert {group["id"]: group["count"] for group in catalog["groups"]} == {
        "v4": 15, "v1": 1035, "v2": 650, "v3": 165,
    }
    cases = [case for group in catalog["groups"] for case in group["cases"]]
    assert len({case["id"] for case in cases}) == 1865
    assert all({"input", "expected", "verification", "execution_path", "raw", "search"} <= case.keys()
               for case in cases)
    assert all(case["execution_path"] for case in cases)
    json.dumps(catalog, ensure_ascii=False)


def test_every_suite_uses_the_same_case_contract():
    required = {"id", "suite", "step_id", "group", "ordinal", "title", "type", "input", "expected",
                "verification", "execution_path", "source", "raw", "execution", "search"}
    samples = {
        "memory": ["tests/memory/unit/test_db.py::test_opens_in_wal"],
        "voice": ["tests/voice/unit/test_attention.py::test_mode_default_is_always"],
        "agent-headless": ["tests/agent_headless/unit/flash/test_router.py::test_route"],
        "browser": ["tests/browser/unit/widgets/test_actions.py::test_action"],
        "connectors": ["tests/connectors/unit/email/test_mailbox.py::test_mailbox"],
        "cluster": ["tests/cluster/unit/test_capsule.py::test_capsule"],
        "infrastructure": ["tests/infrastructure/unit/test_bus.py::test_bus"],
    }
    for suite, tests in samples.items():
        catalog = build_suite_catalog(suite, tests)
        cases = [case for step in catalog["steps"] for group in step["case_groups"] for case in group["cases"]]
        assert cases, suite
        assert all(required <= case.keys() for case in cases), suite


def test_generic_case_resolution_supports_single_cases_and_ordered_groups():
    catalog = build_suite_catalog("memory", ["tests/memory/unit/test_db.py::test_opens_in_wal"])
    single = find_case(catalog, "memory::v1::0000")
    assert single and single["execution"]["kind"] == "command"
    group = find_case(catalog, "memory::group::1.1::pytest")
    assert group and group["execution"]["nodeids"] == ["tests/memory/unit/test_db.py::test_opens_in_wal"]


def test_rich_providers_map_headless_personas():
    headless = build_suite_catalog("agent-headless", [])
    assert find_case(headless, "agent-headless::persona::skeptic")["type"] == "synthetic-dialogue"


def test_memory_gateway_is_primary_and_chronology_replays_its_prefix():
    from tests.memory.e2e.timeline.cases import CASES

    catalog = build_suite_catalog("memory", [])
    assert catalog["steps"][0]["id"] == "1.4"
    dialogue, timeline = catalog["steps"][0]["case_groups"][:2]
    assert dialogue["id"] == "v4"
    assert dialogue["count"] == 15
    assert dialogue["execution"]["stateful"] is True
    last_dialogue = find_case(catalog, "memory::v4::0014")
    assert last_dialogue["execution"]["replay_prefix"] is True
    assert timeline["id"] == "timeline-6m"
    assert timeline["count"] == 1209 == len(CASES)
    rem_days = [case["day"] for case in CASES if case["op"] == "rem"]
    assert rem_days == list(range(1, 271))
    assert timeline["execution"]["stateful"] is True
    last = find_case(catalog, "memory::timeline::0965")
    assert last["execution"]["replay_prefix"] is True


def test_memory_primary_ui_action_runs_the_conversational_gateway():
    """Pressing play on «Memoria» means the conversational gateway, not that suite's pile of unit tests.

    This used to be pinned to a LITERAL in the dashboard's JavaScript
    (`'memory':'memory::group::1.4::v4'`), which put the fact in the only place it could drift from the
    manifest without anything noticing — and on 2026-09-16 a dashboard rewrite dropped the literal and
    silently turned that button into «run every deterministic memory test». The fact now lives in
    `memory/suite.json` like every other suite's, the server publishes it, and the UI reads it; what is
    checked here is the CONTRACT plus the one line of UI that consumes it."""
    assert SUITES["memory"].primary_case == "memory::group::1.4::v4"
    assert find_case(build_suite_catalog("memory", []), SUITES["memory"].primary_case), (
        "el caso principal de memoria no existe en su propio catálogo")
    # And the door that ACTUALLY opens it: `python -m tests run memory`, which is what an agent types.
    # The Observatory has no play button any more (the agents drive the tests), so the UI is no longer
    # where this fact can be checked — nor where it can break.
    source = (ENGINE / "tests/platform/cli.py").read_text(encoding="utf-8")
    assert "requested_case = SUITES[args.suite].primary_case" in source, (
        "`python -m tests run <suite>` ya no cae en el caso principal declarado por la suite")


def test_agent_context_points_to_the_canonical_testing_guide():
    guide = ENGINE / "tests/README.md"
    assert guide.exists()
    assert "http://127.0.0.1:8765" in guide.read_text(encoding="utf-8")
    assert "tests/README.md" in (ENGINE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "tests/README.md" in (ENGINE / "CLAUDE.md").read_text(encoding="utf-8")
    # AGENTS.md is the pointer every other CLI finds; it has to lead somewhere (2026-09-15).
    assert "CLAUDE.md" in (ENGINE / "AGENTS.md").read_text(encoding="utf-8")
