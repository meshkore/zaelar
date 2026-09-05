"""Energy metering for the widget generator's headless Claude Code agent (2026-08-05).

Before this, `_run_agent` discarded stdout entirely (`_, stderr = p.communicate(...)`) even though
`--output-format json` already returns real `usage`/`model` — the SAME shape as the interactive Brain
Workers' stream-json "result" message that DOES get metered (nucleo/workers/session.py). Widget
generation/modification silently cost zero Energy despite spending real tokens.
"""
from unittest.mock import MagicMock, patch

from widgets import generator


class _FakeProc:
    def __init__(self, stdout, returncode=0):
        self._stdout = stdout
        self.returncode = returncode

    def communicate(self, input=None, timeout=None):  # noqa: A002
        return self._stdout, ""


def test_run_agent_reports_worker_usage_from_json_output(monkeypatch, tmp_path):
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    stdout = '{"result": "done", "model": "glm-5.2", "usage": {"input_tokens": 1200, "output_tokens": 340}}'
    monkeypatch.setattr(generator.subprocess, "Popen", lambda *a, **kw: _FakeProc(stdout))
    with patch("nucleo.energy_meter.report_worker_usage") as report:
        ok, err = generator._run_agent("build me a widget", target=str(tmp_path))
    assert ok is True
    assert err == ""
    report.assert_called_once()
    kwargs = report.call_args.kwargs
    assert kwargs["model"] == "glm-5.2"
    assert kwargs["prompt_tokens"] == 1200
    assert kwargs["completion_tokens"] == 340


def test_run_agent_survives_non_json_stdout(monkeypatch, tmp_path):
    """A generation that succeeds but whose stdout isn't parseable JSON must still report ok=True —
    the energy-reporting best-effort block must never turn a successful generation into a failure."""
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(generator.subprocess, "Popen", lambda *a, **kw: _FakeProc("not json at all"))
    with patch("nucleo.energy_meter.report_worker_usage") as report:
        ok, err = generator._run_agent("build me a widget", target=str(tmp_path))
    assert ok is True
    report.assert_not_called()


def test_run_agent_skips_energy_report_without_usage_field(monkeypatch, tmp_path):
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    stdout = '{"result": "done"}'
    monkeypatch.setattr(generator.subprocess, "Popen", lambda *a, **kw: _FakeProc(stdout))
    with patch("nucleo.energy_meter.report_worker_usage") as report:
        ok, err = generator._run_agent("build me a widget", target=str(tmp_path))
    assert ok is True
    report.assert_not_called()
