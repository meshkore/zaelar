#
# test_skeleton.py — el esqueleto del cerebro v2 (V2-001, T37). Verifica que `import nucleo` (y todos sus
# submódulos) funciona y que el CONTRATO está fijado: firmas presentes, stubs que levantan NotImplementedError
# al llamarse (nada cableado a la voz todavía). Ejecutar: .venv/bin/pytest tests/agent_headless/unit/test_skeleton.py
#
import importlib

import pytest


def test_import_tree():
    for mod in [
        "nucleo",
        "nucleo.flash", "nucleo.flash.router", "nucleo.flash.fast_client",
        "nucleo.flash.frontend", "nucleo.flash.procs", "nucleo.flash.escalate",
        "nucleo.loop", "nucleo.dispatch", "nucleo.memory_agent",
        "nucleo.agentes", "nucleo.agentes.base", "nucleo.agentes.claude_code", "nucleo.agentes.codex",
    ]:
        importlib.import_module(mod)


def test_wired_to_voice():
    # V2-004: el FlashBrain ya está cableado a la voz (provider `nucleo`, opt-in BRAIN=nucleo).
    import nucleo
    assert nucleo.WIRED_TO_VOICE is True


def test_fast_client_model_by_invocation():
    from nucleo.flash.fast_client import ModelSpec, FastClient
    spec = ModelSpec(model="x-ai/grok-4-fast-non-reasoning", provider="aimlapi")
    assert spec.model and spec.provider == "aimlapi"
    assert hasattr(FastClient(), "stream")


def test_router_decision_dataclass():
    from nucleo.flash.router import Decision
    d = Decision(kind="escalate", payload={"request": "busca pisos"})
    assert d.kind == "escalate" and d.payload["request"] == "busca pisos"


def test_codeagent_interface_is_abstract():
    from nucleo.agentes.base import CodeAgent, RunSpec, RunResult
    with pytest.raises(TypeError):
        CodeAgent()                      # ABC con run() abstracto → no instanciable
    assert RunSpec(model="m").deny_tools is False
    assert RunResult(ok=True).output == ""


def test_flash_pieces_built():
    # V2-004: las piezas del FlashBrain ya NO son stubs (frontend.show compone tag; escalate registra + emite bus).
    from nucleo.flash import frontend, escalate
    assert frontend.show("agenda") == "[[show:agenda]]"
    tid = escalate.escalate_to_slowbrain("haz algo")
    assert isinstance(tid, int) and tid > 0
    escalate.reset()


def test_slowbrain_built():
    # V2-006: el SlowBrain (agentes CodeAgent + dispatcher + memory_agent) YA está construido.
    # Los adaptadores no lanzan NotImplementedError; devuelven un RunResult limpio (aquí, CLI ausente → ok=False).
    import asyncio
    import os

    from nucleo.agentes import get_agent
    from nucleo.agentes.base import RunResult, RunSpec
    from nucleo.agentes.claude_code import ClaudeCodeAgent

    assert isinstance(get_agent("claude_code"), ClaudeCodeAgent)
    res = asyncio.run(ClaudeCodeAgent().run("hola", spec=RunSpec(model="m", cwd=os.getcwd(), timeout=5)))
    assert isinstance(res, RunResult)
