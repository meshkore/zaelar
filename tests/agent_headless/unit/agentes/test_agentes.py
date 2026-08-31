#
# test_agentes.py — the CodeAgent interface + adapters + selection by config (V2-006, T77-T79).
# Verifies: ABC/RunSpec contract, real Claude Code adapter against a FAKE CLI (model per invocation +
# tool policy + JSON output parsing + timeout), Codex stub that responds without launching, and the
# get_agent() factory by config. Run: .venv/bin/pytest tests/agent_headless/unit/agentes/test_agentes.py
#
import asyncio
import os
import stat

import pytest

from nucleo.agentes import get_agent
from nucleo.agentes.base import CodeAgent, RunResult, RunSpec
from nucleo.agentes.claude_code import ClaudeCodeAgent
from nucleo.agentes.codex import CodexAgent


def test_widget_action_modify_vs_create(monkeypatch):
    """SINGLE SOURCE OF TRUTH for create/modify/delete (§2026-07-15). Regression: 'implementar en el widget youtube …' without
    a MODIFY verb fell through to CREATE → junk widget. Now: existing + no explicit 'crear' = MODIFY."""
    from nucleo.agentes import code
    # existing widget resolved by identify (mocked to avoid depending on the catalog)
    monkeypatch.setattr(code, "_referenced_widget", lambda r: "youtube" if "youtube" in r.lower() else "")
    assert code.widget_action("Implementar en el widget youtube la capacidad de ampliarse por voz") == ("modify", "youtube")
    assert code.widget_action("añade pantalla completa al widget youtube") == ("modify", "youtube")
    assert code.widget_action("borra el widget youtube") == ("delete", "youtube")
    assert code.widget_action("créame un widget nuevo del tiempo") == ("create", "")   # does not exist → create
    # existing BUT with an explicit create verb → create (e.g. "crea otro youtube")
    assert code.widget_action("crea otro widget youtube distinto")[0] == "create"


def test_codeagent_is_abstract():
    with pytest.raises(TypeError):
        CodeAgent()                                   # run() abstract → cannot be instantiated


def test_runspec_defaults():
    s = RunSpec()
    assert s.model == "" and s.tools is None and s.deny_tools is False and s.timeout == 600.0
    assert RunResult(ok=True).output == ""


# ── FAKE Claude CLI: records its argv + stdin, prints JSON like `claude -p --output-format json`. ──
_FAKE_CLAUDE = r"""#!/usr/bin/env python3
import sys, json, os
argv = sys.argv[1:]
stdin = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "w", encoding="utf-8") as f:
    f.write(json.dumps({"argv": argv, "stdin": stdin}))
if os.environ.get("FAKE_SLEEP"):
    import time; time.sleep(float(os.environ["FAKE_SLEEP"]))
if os.environ.get("FAKE_RC"):
    sys.stderr.write("boom"); sys.exit(int(os.environ["FAKE_RC"]))
print(json.dumps({"result": "RESPUESTA DEL AGENTE: " + stdin.strip()[:40]}))
"""


@pytest.fixture()
def fake_claude(tmp_path, monkeypatch):
    p = tmp_path / "claude"
    p.write_text(_FAKE_CLAUDE, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "call.json"
    monkeypatch.setenv("CLAUDE_BIN", str(p))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.delenv("FAKE_RC", raising=False)
    monkeypatch.delenv("FAKE_SLEEP", raising=False)
    return {"bin": p, "log": log}


def test_claude_run_passes_model_and_parses_output(fake_claude, tmp_path):
    import json
    res = asyncio.run(ClaudeCodeAgent().run(
        "haz un resumen", spec=RunSpec(model="modelo-de-prueba", cwd=str(tmp_path), timeout=10)))
    assert res.ok is True
    assert "RESPUESTA DEL AGENTE" in res.output          # parsed the JSON `result` field
    call = json.loads(fake_claude["log"].read_text(encoding="utf-8"))
    assert "haz un resumen" in call["stdin"]              # prompt via STDIN
    assert "--model" in call["argv"] and "modelo-de-prueba" in call["argv"]   # MODEL PER INVOCATION
    # default tools = read-only + bridge CLIs (V2-036); NEVER a bare "Bash"
    # (assertion updated in the 2026-07-14 audit: it became outdated when the bridges were added)
    import re
    ai = call["argv"].index("--allowedTools")
    allowed = call["argv"][ai + 1]
    assert allowed.startswith("Read")
    assert not re.search(r"\bBash\b(?!\()", allowed)      # no unrestricted Bash (only Bash(…) restricted to CLIs)


def test_claude_deny_tools_means_no_tools(fake_claude, tmp_path):
    import json
    asyncio.run(ClaudeCodeAgent().run(
        "texto no confiable", spec=RunSpec(model="m", cwd=str(tmp_path), deny_tools=True, tools=["Bash"])))
    call = json.loads(fake_claude["log"].read_text(encoding="utf-8"))
    ai = call["argv"].index("--allowedTools")
    assert call["argv"][ai + 1] == ""                    # deny_tools → NONE, ignores the allowlist


def test_claude_timeout(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "2")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", cwd=str(tmp_path), timeout=0.3)))
    assert res.ok is False and "timeout" in res.error.lower()


def test_claude_nonzero_exit(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_RC", "2")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", cwd=str(tmp_path), timeout=10)))
    assert res.ok is False and res.meta.get("returncode") == 2


def test_claude_cli_missing_is_clean(monkeypatch):
    # robustly forces "no CLI" (this dev machine DOES have claude in PATH/glob).
    monkeypatch.setattr("nucleo.agentes.claude_code._find_claude", lambda: "")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", timeout=5)))
    assert res.ok is False and "no encontrado" in res.error.lower()


def test_codex_missing_responds_without_raising(monkeypatch):
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    res = asyncio.run(CodexAgent().run("x", spec=RunSpec(model="m", timeout=5)))
    assert isinstance(res, RunResult) and res.ok is False       # signature intact, no NotImplementedError


def test_get_agent_by_config(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "codex")
    # config/v2 reads the fallback env if the store is silent (nonexistent file → empty store)
    import config.v2 as v2
    monkeypatch.setattr(v2, "_PATH", tmp_path / "none.json")
    assert isinstance(get_agent(), CodexAgent)
    assert isinstance(get_agent("claude_code"), ClaudeCodeAgent)
    assert isinstance(get_agent("desconocido"), ClaudeCodeAgent)   # fallback to the default, without crashing
