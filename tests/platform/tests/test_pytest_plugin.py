from tests.platform.pytest_plugin import _suite


def test_suite_is_derived_from_domain_first_path(monkeypatch):
    monkeypatch.setenv("ZAELAR_TEST_SUITE", "all")
    assert _suite("tests/memory/unit/test_db.py::test_open") == "memory"
    assert _suite("tests/agent_headless/unit/test_loop.py::test_turn") == "agent-headless"
    assert _suite("tests/browser/unit/agenda/test_xss_contract.py::test_xss") == "browser"
    assert _suite("tests/cluster/unit/test_security.py::test_guard") == "cluster"
    assert _suite("tests/platform/tests/test_events.py::test_writer") == "infrastructure"


def test_explicit_suite_wins_for_single_suite_runs(monkeypatch):
    monkeypatch.setenv("ZAELAR_TEST_SUITE", "voice")
    assert _suite("tests/voice/unit/test_trace.py::test_trace") == "voice"
