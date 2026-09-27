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


def test_the_generator_rides_the_workers_chain_and_relays_once(monkeypatch, tmp_path):
    """Same chain as the Brain Workers: the tier that ran out is noted and the next one builds the widget."""
    from nucleo.workers import providers
    tiers = [{"name": "z.ai", "base_url": "https://z.example/anthropic", "model": "glm-5.3"},
             {"name": "deepseek", "base_url": "https://ds.example/anthropic", "model": "deepseek-flash"}]
    state = {"i": 0}
    monkeypatch.setattr(providers, "pick", lambda: tiers[state["i"]])
    monkeypatch.setattr(providers, "env_for_worker", lambda: {
        "ANTHROPIC_BASE_URL": tiers[state["i"]]["base_url"], "ANTHROPIC_AUTH_TOKEN": "t"})

    def _noted(text, tier):
        state["i"] = 1
        return {"kind": "exhausted", "provider": tier["name"], "next": "deepseek", "detail": ""}
    monkeypatch.setattr(providers, "note_failure", _noted)
    spawned = []

    class _P:
        def __init__(self, cmd, **kw):
            spawned.append((kw["env"]["ANTHROPIC_BASE_URL"], cmd[cmd.index("--model") + 1]))
            self.returncode = 1 if len(spawned) == 1 else 0

        def communicate(self, input=None, timeout=None):  # noqa: A002
            if self.returncode:
                return '{"is_error":true,"result":"API Error (429) Weekly/Monthly Limit Exhausted"}', ""
            return '{"result":"DONE"}', ""
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(generator.subprocess, "Popen", _P)
    ran, err = generator._run_agent("build it", target=str(tmp_path))
    assert ran is True and err == ""
    assert spawned == [("https://z.example/anthropic", "glm-5.3"), ("https://ds.example/anthropic", "deepseek-flash")]


def test_a_build_error_is_not_relayed(monkeypatch, tmp_path):
    """Only a PROVIDER failure moves to another tier; our own bug would fail identically everywhere."""
    from nucleo.workers import providers
    monkeypatch.setattr(providers, "note_failure", lambda *a: pytest.fail("an 'ours' failure was relayed"))

    class _P(_Proc):
        def communicate(self, input=None, timeout=None):  # noqa: A002
            return '{"is_error":true,"result":"TypeError: cannot read the manifest"}', ""
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(generator.subprocess, "Popen", _P)
    ran, err = generator._run_agent("build it", target=str(tmp_path))
    assert ran is False and generator.failure_class(err) == "ours"
