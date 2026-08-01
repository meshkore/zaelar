#
# test_agentes.py — la interfaz CodeAgent + adaptadores + selección por config (V2-006, T77-T79).
# Verifica: contrato ABC/RunSpec, adaptador Claude Code real contra un CLI FALSO (modelo por invocación +
# política de tools + parseo de salida JSON + timeout), stub de Codex que responde sin lanzar, y la factoría
# get_agent() por config. Ejecutar: .venv/bin/pytest tests/agent_headless/unit/agentes/test_agentes.py
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
    """FUENTE ÚNICA crear/modificar/borrar (§2026-07-15). Regresión: 'implementar en el widget youtube …' sin
    verbo de MODIFICAR caía a CREATE → widget basura. Ahora: existente + sin 'crear' explícito = MODIFY."""
    from nucleo.agentes import code
    # widget existente resuelto por identify (mockeado para no depender del catálogo)
    monkeypatch.setattr(code, "_referenced_widget", lambda r: "youtube" if "youtube" in r.lower() else "")
    assert code.widget_action("Implementar en el widget youtube la capacidad de ampliarse por voz") == ("modify", "youtube")
    assert code.widget_action("añade pantalla completa al widget youtube") == ("modify", "youtube")
    assert code.widget_action("borra el widget youtube") == ("delete", "youtube")
    assert code.widget_action("créame un widget nuevo del tiempo") == ("create", "")   # no existe → create
    # existente PERO con verbo de crear explícito → create (p.ej. "crea otro youtube")
    assert code.widget_action("crea otro widget youtube distinto")[0] == "create"


def test_codeagent_is_abstract():
    with pytest.raises(TypeError):
        CodeAgent()                                   # run() abstracto → no instanciable


def test_runspec_defaults():
    s = RunSpec()
    assert s.model == "" and s.tools is None and s.deny_tools is False and s.timeout == 600.0
    assert RunResult(ok=True).output == ""


# ── CLI de Claude FALSO: registra su argv + su stdin, imprime un JSON tipo `claude -p --output-format json`. ──
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
        "haz un resumen", spec=RunSpec(model="haiku-test", cwd=str(tmp_path), timeout=10)))
    assert res.ok is True
    assert "RESPUESTA DEL AGENTE" in res.output          # parseó el campo `result` del JSON
    call = json.loads(fake_claude["log"].read_text(encoding="utf-8"))
    assert "haz un resumen" in call["stdin"]              # prompt por STDIN
    assert "--model" in call["argv"] and "haiku-test" in call["argv"]   # MODELO POR INVOCACIÓN
    # tools por defecto = solo lectura + los CLIs puente (V2-036); NUNCA un "Bash" pelado
    # (aserción actualizada en la auditoría 2026-07-14: quedó vieja cuando entraron los puentes)
    import re
    ai = call["argv"].index("--allowedTools")
    allowed = call["argv"][ai + 1]
    assert allowed.startswith("Read")
    assert not re.search(r"\bBash\b(?!\()", allowed)      # sin Bash abierto (solo Bash(…) acotado a CLIs)


def test_claude_deny_tools_means_no_tools(fake_claude, tmp_path):
    import json
    asyncio.run(ClaudeCodeAgent().run(
        "texto no confiable", spec=RunSpec(model="m", cwd=str(tmp_path), deny_tools=True, tools=["Bash"])))
    call = json.loads(fake_claude["log"].read_text(encoding="utf-8"))
    ai = call["argv"].index("--allowedTools")
    assert call["argv"][ai + 1] == ""                    # deny_tools → NINGUNA, ignora la allowlist


def test_claude_timeout(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "2")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", cwd=str(tmp_path), timeout=0.3)))
    assert res.ok is False and "timeout" in res.error.lower()


def test_claude_nonzero_exit(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_RC", "2")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", cwd=str(tmp_path), timeout=10)))
    assert res.ok is False and res.meta.get("returncode") == 2


def test_claude_cli_missing_is_clean(monkeypatch):
    # fuerza "sin CLI" de forma robusta (esta máquina de dev SÍ tiene claude en el PATH/glob).
    monkeypatch.setattr("nucleo.agentes.claude_code._find_claude", lambda: "")
    res = asyncio.run(ClaudeCodeAgent().run("x", spec=RunSpec(model="m", timeout=5)))
    assert res.ok is False and "no encontrado" in res.error.lower()


def test_codex_missing_responds_without_raising(monkeypatch):
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    res = asyncio.run(CodexAgent().run("x", spec=RunSpec(model="m", timeout=5)))
    assert isinstance(res, RunResult) and res.ok is False       # firma intacta, no NotImplementedError


def test_get_agent_by_config(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_AGENT_PROVIDER", "codex")
    # config/v2 lee el env de fallback si el store está en silencio (fichero inexistente → store vacío)
    import config.v2 as v2
    monkeypatch.setattr(v2, "_PATH", tmp_path / "none.json")
    assert isinstance(get_agent(), CodexAgent)
    assert isinstance(get_agent("claude_code"), ClaudeCodeAgent)
    assert isinstance(get_agent("desconocido"), ClaudeCodeAgent)   # fallback al default, sin reventar
