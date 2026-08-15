"""Tests de nucleo/flash/fast_client.py (V2-004 · T60) — modelo por invocación, streaming, tool-calls, UA-spoof."""
import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import fast_client as fc
from nucleo.flash.fast_client import FastClient, ModelSpec


# ── fakes que imitan la superficie de streaming de OpenAI ────────────────────────────────────────────────
def _delta(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _chunk(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=_delta(content, tool_calls))])


def _tool_call(index, name=None, args=None):
    return SimpleNamespace(index=index, function=SimpleNamespace(name=name, arguments=args))


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


class _FakeCompletions:
    def __init__(self, chunks, recorder):
        self._chunks = chunks
        self._rec = recorder

    async def create(self, **kwargs):
        self._rec.update(kwargs)
        return _FakeStream(self._chunks)


class _FakeClient:
    def __init__(self, chunks, recorder):
        self.chat = SimpleNamespace(completions=_FakeCompletions(chunks, recorder))


def _patch_client(monkeypatch, chunks, recorder):
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: _FakeClient(chunks, recorder))


# ── ModelSpec ────────────────────────────────────────────────────────────────────────────────────────────
def test_modelspec_local_vs_cloud():
    local = ModelSpec(model="qwen2.5:14b", provider="ollama")
    assert local.is_local()
    assert local.resolved_api_key() == "ollama"
    assert "11434" in local.resolved_base_url()

    cloud = ModelSpec(model="x-ai/grok-4-fast-non-reasoning", provider="aimlapi", api_key="k")
    assert not cloud.is_local()
    assert cloud.resolved_api_key() == "k"
    assert "aimlapi" in cloud.resolved_base_url()


def test_reasoning_effort_gemini_only():
    gem = ModelSpec(model="gemini-2.5-flash", base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key="k")
    assert gem.reasoning_effort() == "none"
    aiml = ModelSpec(model="deepseek/deepseek-v4-flash", provider="aimlapi", api_key="k")
    assert aiml.reasoning_effort() == ""


# ── streaming de texto ──────────────────────────────────────────────────────────────────────────────────
def test_stream_yields_text(monkeypatch):
    rec = {}
    _patch_client(monkeypatch, [_chunk("Hola"), _chunk(" mundo")], rec)

    async def run():
        out = []
        async for t in FastClient().stream([{"role": "user", "content": "hi"}],
                                           spec=ModelSpec(model="m", api_key="k")):
            out.append(t)
        return out

    assert asyncio.run(run()) == ["Hola", " mundo"]


def test_stream_tracks_inflight_around_the_network_call(monkeypatch):
    """V2-092 addenda (2026-08-15): the ⏻ switch's deferred stop needs to know when a real model call is in
    flight, so it can wait for it to finish instead of cutting it mid-response or waiting on a timer. `stream()`
    must bracket the whole call — `enter_inflight()` before, `exit_inflight()` after — regardless of which
    branch of `_stream_inner` actually runs. See `nucleo/runstate.py` for the counter itself."""
    rec = {}
    _patch_client(monkeypatch, [_chunk("hola")], rec)
    from nucleo import runstate
    calls = []
    monkeypatch.setattr(runstate, "enter_inflight", lambda: calls.append("enter"))

    async def fake_exit():
        calls.append("exit")
    monkeypatch.setattr(runstate, "exit_inflight", fake_exit)

    async def run():
        out = []
        async for t in FastClient().stream([{"role": "user", "content": "hi"}],
                                           spec=ModelSpec(model="m", api_key="k")):
            out.append(t)
            assert calls == ["enter"], "exit_inflight must not fire before the stream is done yielding"
        return out

    assert asyncio.run(run()) == ["hola"]
    assert calls == ["enter", "exit"]


def test_model_passed_per_invocation(monkeypatch):
    """El modelo del spec llega al request — no una env global."""
    rec = {}
    _patch_client(monkeypatch, [_chunk("ok")], rec)

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}],
                                           spec=ModelSpec(model="MI-MODELO-XYZ", api_key="k")):
            pass

    asyncio.run(run())
    assert rec["model"] == "MI-MODELO-XYZ"
    assert rec["stream"] is True


def test_local_spec_sets_keep_alive(monkeypatch):
    rec = {}
    _patch_client(monkeypatch, [_chunk("ok")], rec)

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}],
                                           spec=ModelSpec(model="qwen2.5:14b", provider="ollama")):
            pass

    asyncio.run(run())
    assert rec.get("extra_body", {}).get("keep_alive") == "30m"


# ── tool-calling ────────────────────────────────────────────────────────────────────────────────────────
def test_tool_calls_accumulated_and_fired(monkeypatch):
    rec = {}
    chunks = [
        _chunk(content="me pongo"),
        _chunk(tool_calls=[_tool_call(0, name="escalate_to_slowbrain", args='{"request": "arre')]),
        _chunk(tool_calls=[_tool_call(0, args='gla el bug"}')]),
    ]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], on_tool_call=lambda n, a: fired.append((n, a))):
            pass

    asyncio.run(run())
    assert rec.get("tool_choice") == "auto"
    assert fired == [("escalate_to_slowbrain", {"request": "arregla el bug"})]


def test_bad_tool_args_skipped_not_raised(monkeypatch):
    rec = {}
    chunks = [_chunk(tool_calls=[_tool_call(0, name="f", args="{not json")])]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], on_tool_call=lambda n, a: fired.append(n)):
            pass

    asyncio.run(run())          # no lanza
    assert fired == []          # se salta la llamada con JSON inválido


def test_tool_call_fired_on_early_return(monkeypatch):
    """El consumidor corta el bucle (GeneratorExit) → la tool call ya acumulada NO se pierde (finally)."""
    rec = {}
    chunks = [
        _chunk(tool_calls=[_tool_call(0, name="escalate_to_slowbrain", args='{"request":"x"}')]),
        _chunk(content="STOP"),
        _chunk(content="más"),
    ]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for t in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], on_tool_call=lambda n, a: fired.append(n)):
            if t == "STOP":
                return

    asyncio.run(run())
    assert fired == ["escalate_to_slowbrain"]


# ── spec_from_config ────────────────────────────────────────────────────────────────────────────────────
def test_spec_from_config_reads_v2(monkeypatch):
    monkeypatch.setattr("config.v2.fast_model_spec",
                        lambda: {"provider": "ollama", "model": "qwen2.5:14b", "base_url": "", "api_key": ""})
    spec = fc.spec_from_config()
    assert spec.model == "qwen2.5:14b"
    assert spec.provider == "ollama"
    assert spec.is_local()


def test_spec_from_config_fallback_is_never_grok(monkeypatch):
    # auditoría 2026-07-26: el fallback (config sin modelo, o config.v2 rota) NUNCA debe caer en grok — está
    # BANEADO en el FlashBrain (mis-rutea memoria→widget_data). Cubre ambas ramas: dict sin "model" y excepción.
    monkeypatch.setattr("config.v2.fast_model_spec",
                        lambda: {"provider": "aimlapi", "model": "", "base_url": "", "api_key": ""})
    assert "grok" not in fc.spec_from_config().model.lower()

    def _boom():
        raise RuntimeError("config rota")
    monkeypatch.setattr("config.v2.fast_model_spec", _boom)
    spec = fc.spec_from_config()
    assert "grok" not in spec.model.lower()
    assert spec.model == fc._FALLBACK_MODEL
