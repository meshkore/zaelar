from pathlib import Path

from tests.platform.catalog import SUITES, build_suite_catalog, deterministic_paths, find_case
from tests.memory.e2e.bot.catalog import build_catalog


ENGINE = Path(__file__).resolve().parents[3]


def test_every_catalogued_path_exists():
    missing = [path for path in deterministic_paths("all") if not (ENGINE / path).exists()]
    assert missing == []


def test_core_operator_suites_are_declared():
    assert {"journey", "memory", "agent-headless", "voice", "browser"}.issubset(SUITES)


def test_memory_request_catalog_is_complete_and_json_safe():
    import json

    catalog = build_catalog()
    assert catalog["total"] == 1862
    assert {group["id"]: group["count"] for group in catalog["groups"]} == {
        "v4": 15, "v1": 1032, "v2": 650, "v3": 165,
    }
    cases = [case for group in catalog["groups"] for case in group["cases"]]
    assert len({case["id"] for case in cases}) == 1862
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


def test_rich_providers_map_voice_and_headless_cases():
    voice = build_suite_catalog("voice", [])
    headless = build_suite_catalog("agent-headless", [])
    assert find_case(voice, "voice::scenario::agenda")["input"]["channel"] == "voice"
    assert find_case(headless, "agent-headless::persona::skeptic")["type"] == "synthetic-dialogue"
    assert find_case(headless, "agent-headless::search::0000")["type"] == "routing"


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
    dashboard = (ENGINE / "tests/platform/dashboard/index.html").read_text(encoding="utf-8")
    assert "'memory':'memory::group::1.4::v4'" in dashboard
    assert "▶ Ejecutar gateway · Memoria" in dashboard
    assert "◇ Ejecutar componentes" in dashboard


def test_whole_system_journey_is_causal_mapped_and_primary():
    from tests.journey.catalog import load_plan

    plan = load_plan()
    produced = set()
    for case in plan["cases"]:
        assert set(case.get("consumes", [])) <= produced, case["id"]
        produced.update(case.get("produces", []))
    # 26 original cases + 3 for connecting to clusters (V2-086: recognize without acting → authorize →
    # native-surface contract). When adding a step to the journey, this number AND `case_count` in suite.json
    # must be updated.
    assert len(plan["cases"]) == 29
    assert {case["channel"] for case in plan["cases"]} >= {
        "headless", "browser-api", "observer", "meshkore-http", "meshkore", "http",
    }
    catalog = build_suite_catalog("journey", [])
    group = catalog["steps"][0]["case_groups"][0]
    assert group["count"] == 29
    assert group["execution"]["isolated_workspace"] is True
    last = find_case(catalog, "journey::whole-system-v1::0028")
    assert last["execution"]["replay_prefix"] is True
    assert SUITES["journey"].primary_case == "journey::group::10.1::whole-system-v1"
    assert SUITES["journey"].case_count == 29
    dashboard = (ENGINE / "tests/platform/dashboard/index.html").read_text(encoding="utf-8")
    assert "'journey':'journey::group::10.1::whole-system-v1'" in dashboard


def test_agent_context_points_to_the_canonical_testing_guide():
    guide = ENGINE / "tests/README.md"
    assert guide.exists()
    assert "http://127.0.0.1:8765" in guide.read_text(encoding="utf-8")
    assert "tests/README.md" in (ENGINE / "CLAUDE.md").read_text(encoding="utf-8")
    assert "tests/README.md" in (ENGINE / "AGENTS.md").read_text(encoding="utf-8")
