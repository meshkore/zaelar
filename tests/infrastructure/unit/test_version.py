#
# Version stamp (V2-074). Run: .venv/bin/pytest tests/infrastructure/unit/test_version.py -q
#
# Certainty about what code is running and which version generated each observability line: version.info() is well
# formed and the observer stamps EVERY event with `ver`.
#
import json
import os

import version


def test_version_info_shape():
    info = version.info()
    for k in ("version", "sha", "short", "started_ms", "uptime_s"):
        assert k in info
    assert info["short"] == f"{info['version']}+{info['sha']}"
    assert isinstance(info["started_ms"], int) and info["started_ms"] > 0


def test_short_is_stable():
    assert version.short() == version.short()          # cached, stable within the process


def test_observer_stamps_version(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_LOG_DIR", str(tmp_path))
    import importlib
    from voice import observer
    importlib.reload(observer)                          # rereads LOG_DIR
    observer.emit("test", "hola", "mundo")
    observer._write_q.join()                            # waits for the OFF-THREAD writer (V2-035) before reading
    line = (tmp_path / "timeline-latest.jsonl").read_text().strip().splitlines()[-1]
    ev = json.loads(line)
    assert ev.get("ver") == version.short()
