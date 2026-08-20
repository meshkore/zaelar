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


# ── V2-171: una acción descartada es un HECHO, no un `continue` ───────────────────────────────────────────
#
# Medido el 2026-08-20 contra el titular real (deepseek-v4-pro): el turno corría con `max_tokens=200`, y una
# escalada bien escrita ocupa ~1000-1400 caracteres de JSON ella sola. El proveedor cortaba con
# `finish_reason="length"`, los argumentos llegaban a medias, `json.loads` reventaba y el `except` hacía
# `continue`. 67 acciones perdidas en 27 corridas, 48 de ellas escaladas que nunca llegaron a un Brain Worker.
# Desde fuera se leía como que zaelar prometía y no hacía. No mentía: le tiraban la acción.
def _chunk_fr(reason):
    return SimpleNamespace(choices=[SimpleNamespace(delta=_delta(None, None), finish_reason=reason)])


def test_the_cap_fits_the_most_important_tool_call():
    """El tope tiene que caber una escalada COMPLETA. Medido: 972-1408 caracteres de JSON, más la frase que
    zaelar dice en voz alta. Y subirlo no cuesta latencia —también medido, 3 corridas por brazo: TTFT 0,99s a
    200 y 0,91s a 1200, con la MISMA respuesta— porque un tope es un techo, no un objetivo."""
    from nucleo.flash import fast_client as fc

    assert fc._DEFAULT_MAX_TOKENS >= 1000


def test_the_stream_records_WHY_it_ended(monkeypatch):
    """El dato que convertía esto en un misterio: sin `finish_reason`, un corte por tope y un final limpio son
    indistinguibles desde dentro del bucle."""
    rec, m = {}, {}
    _patch_client(monkeypatch, [_chunk(content="ok"), _chunk_fr("length")], rec)

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}],
                                           spec=ModelSpec(model="m", api_key="k"), metrics=m):
            pass

    asyncio.run(run())
    assert m.get("finish_reason") == "length"


def test_a_truncated_tool_call_leaves_a_trace_instead_of_vanishing(monkeypatch):
    rec, m = {}, {}
    chunks = [_chunk(tool_calls=[_tool_call(0, name="escalate_to_slowbrain", args='{"request": "busca un moni')]),
              _chunk_fr("length")]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], metrics=m,
                                           on_tool_call=lambda n, a: fired.append(n)):
            pass

    asyncio.run(run())
    assert fired == []                                   # sigue sin ejecutarse: los argumentos no son legibles
    dropped = m.get("dropped_tool_calls") or []
    assert len(dropped) == 1
    assert dropped[0]["name"] == "escalate_to_slowbrain"
    assert "tope" in dropped[0]["reason"]                 # y dice POR QUÉ, que es lo que faltaba


def test_and_says_so_where_the_operator_can_see_it(monkeypatch):
    """Mientras el fallo solo viviera en un `logger.warning`, ni el operador, ni el juez, ni el Master lo veían."""
    from voice import observer

    seen = []
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})))
    rec, m = {}, {}
    _patch_client(monkeypatch, [_chunk(tool_calls=[_tool_call(0, name="show_widget", args='{"widget_id": "resu')])], rec)

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], metrics=m, on_tool_call=lambda n, a: None):
            pass

    asyncio.run(run())
    assert any(extra.get("tool") == "show_widget" for _k, _l, extra in seen)


def test_but_a_tool_call_that_parses_is_untouched(monkeypatch):
    """La sensibilidad de todo lo anterior: sin esto, «reporta los descartes» y «reporta siempre» pasan igual."""
    rec, m = {}, {}
    chunks = [_chunk(tool_calls=[_tool_call(0, name="recall", args='{"query": "monitor"}')]), _chunk_fr("tool_calls")]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], metrics=m,
                                           on_tool_call=lambda n, a: fired.append((n, a))):
            pass

    asyncio.run(run())
    assert fired == [("recall", {"query": "monitor"})]
    assert not m.get("dropped_tool_calls")


# ── V2-176 frente 2: la acción descartada tiene que llegar al TURNO SIGUIENTE ──────────────────────────────────────
#
# V2-171 dejó el descarte en las métricas del turno y en observabilidad — donde el operador puede mirarlo
# DESPUÉS. Pero la frase («te pongo con ello») ya se dijo en ese mismo turno, así que lo único que todavía se
# puede arreglar es el turno de después… y ése no veía nada. La conversación continuaba como si la orden
# hubiera salido, que es el corazón de V2-176: narrar un trabajo que no ocurrió.
#
# Mismo remedio que `tasks.recently_finished()` (V2-150) y `dispatch._EXPIRED_CONFIRM` (V2-190): un hecho que
# solo vive un turno es un hecho que la conversación pierde.
def test_a_dropped_action_survives_the_turn_that_lost_it():
    from nucleo.flash import fast_client as fc

    fc.clear_drops()
    fc._drop_tool_call({"finish_reason": "length"}, "escalate_to_slowbrain", '{"request": "busca un moni')
    drops = fc.recent_drops()
    assert [d["name"] for d in drops] == ["escalate_to_slowbrain"]
    fc.clear_drops()


def test_and_reaches_the_live_state_saying_it_did_NOT_happen():
    from nucleo.flash import fast_client as fc
    from nucleo.flash import prompt as _p

    fc.clear_drops()
    fc._drop_tool_call({"finish_reason": "length"}, "escalate_to_slowbrain", "{bad")
    state = _p.live_state()
    assert "NO LLEGÓ A EJECUTARSE" in state
    assert "escalate_to_slowbrain" in state
    assert "no va a pasar solo" in state
    fc.clear_drops()


def test_but_it_is_said_ONCE_and_not_forever():
    """Un hecho que se repite en cada estado deja de ser un hecho y pasa a ser ruido — y este ya se dijo."""
    from nucleo.flash import fast_client as fc
    from nucleo.flash import prompt as _p

    fc.clear_drops()
    fc._drop_tool_call({}, "show_widget", "{bad")
    assert "NO LLEGÓ A EJECUTARSE" in _p.live_state()
    assert "NO LLEGÓ A EJECUTARSE" not in _p.live_state()
    fc.clear_drops()


def test_and_an_old_drop_is_not_this_conversation():
    import time as _t

    from nucleo.flash import fast_client as fc

    fc.clear_drops()
    fc._drop_tool_call({}, "recall", "{bad")
    fc._RECENT_DROPS[-1]["at"] = _t.time() - (fc._DROP_MEMORY_S + 60)
    assert fc.recent_drops() == []
    fc.clear_drops()


def test_and_a_turn_with_nothing_dropped_says_nothing():
    """La sensibilidad: sin esto, «avisa del descarte» y «avisa siempre» pasan igual."""
    from nucleo.flash import fast_client as fc
    from nucleo.flash import prompt as _p

    fc.clear_drops()
    assert "NO LLEGÓ A EJECUTARSE" not in _p.live_state()
