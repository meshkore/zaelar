import pytest


@pytest.fixture(autouse=True)
def _isolated_meshkore_logs(tmp_path, monkeypatch):
    """These tests drive a real ClusterBridge end to end with FAKE clusters/peers ("arena", "eve", "mallory",
    prompt-injection payloads...) — and neither journal.py nor observer.py had a test-isolation knob (unlike
    bus/log.py's ZAELAR_DB or nucleo/workspace.py's ZAELAR_WORKSPACE), so every run appended this fake
    attack-simulation data straight into the SAME .meshkore/logs/meshkore.jsonl and timeline-latest.jsonl the
    live server/operator read for real post-mortems — indistinguishable from an actual incident. Redirect both
    to a throwaway path for every test in this package.
    """
    from connectors.meshkore import journal
    from voice import observer

    monkeypatch.setattr(journal, "LOG_FILE", tmp_path / "meshkore-test.jsonl")
    monkeypatch.setattr(observer, "LOG_DIR", str(tmp_path))
