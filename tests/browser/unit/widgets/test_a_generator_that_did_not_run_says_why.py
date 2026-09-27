"""V2-776 D4 — a widget build whose agent never ran says WHY, in a class a person can act on.

Measured 2026-09-27 (session 3a9a082c, 12:49 and 15:47): the generator's `claude` exited 1 in three seconds,
twice. `_run_agent` fell through to «ran», the gate answered «no manifest.json produced», a repair pass was
spent on nothing, and the CLI's own error — which `--output-format json` writes to STDOUT — was never read.
The operator heard «No pude crear el widget» and nobody could say whether it was the network, the quota, the
key or us.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.failure_class import classify
from widgets import generator


@pytest.mark.parametrize("text,cls", [
    ("[Errno 8] nodename nor servname provided, or not known", "network"),
    ("httpx.ConnectError: Connection refused", "network"),
    ("API Error: Request rejected (429) · [1310][Weekly/Monthly Limit Exhausted. Your limit will reset", "credit"),
    ("402 Payment Required: insufficient balance", "credit"),
    ("Invalid API key · Please run /login", "auth"),
    ("HTTP 401 Unauthorized", "auth"),
    ("429 Too Many Requests", "rate"),
    ("", "ours"),
    ("KeyError: 'manifest'", "ours"),
])
def test_every_failure_lands_in_one_actionable_class(text, cls):
    assert classify(text) == cls


class _Proc:
    calls = 0

    def __init__(self, *a, **k):
        type(self).calls += 1
        self.returncode = 1

    def communicate(self, input=None, timeout=None):  # noqa: A002
        return '{"type":"result","is_error":true,"result":"Claude AI usage limit reached|1790520000"}', ""


def test_a_cli_that_exits_1_did_not_run(monkeypatch, tmp_path):
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(generator.subprocess, "Popen", _Proc)
    ran, err = generator._run_agent("build it", target=str(tmp_path))
    assert ran is False
    assert "usage limit reached" in err and generator.failure_class(err) == "credit"


def test_a_build_that_never_ran_is_not_repaired_and_carries_its_class(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    _Proc.calls = 0
    monkeypatch.setattr(generator.subprocess, "Popen", _Proc)
    res = generator.generate_widget("un widget de contabilidad con gráficos", wid="contabilidad-test")
    assert res["ok"] is False
    assert res["error_class"] == "credit"
    assert _Proc.calls == 1, "a repair pass was spent on an agent that never ran"


def test_the_worker_session_records_the_class_and_says_it(monkeypatch):
    """The wiring to the row and to the operator: the backend's result reaches `rec.error_class`."""
    from nucleo.workers.generator_session import GeneratorBackend
    from nucleo.workers.session import SessionRecord, WorkerSession
    from nucleo.agentes import code as _code
    monkeypatch.setattr(_code, "widget_action", lambda req: ("create", ""))
    monkeypatch.setattr(generator, "generate_widget", lambda *a, **k: {
        "ok": False, "error": "agent failed [credit]: usage limit reached", "error_class": "credit"})
    rec = SessionRecord(task_id="g1", goal="hazme un widget de contabilidad", kind="code")
    spec = type("S", (), {"model": "", "kind": "code", "task_id": "g1",
                          "env": {"ZAELAR_TASK_REQUEST": "hazme un widget de contabilidad"}})()
    s = WorkerSession(GeneratorBackend(), spec, rec)
    asyncio.run(asyncio.wait_for(s.run("hazme un widget de contabilidad"), timeout=10))
    assert rec.error_class == "credit"
    assert "saldo" in rec.result_summary
