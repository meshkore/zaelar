"""Tests for nucleo/flash/fast_client.py (V2-004 · T60) — per-invocation model, streaming, tool calls, UA spoofing."""
import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import fast_client as fc
from nucleo.flash.fast_client import FastClient, ModelSpec


# ── fakes that imitate OpenAI's streaming interface ─────────────────────────────────────────────────────
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


# ── text streaming ──────────────────────────────────────────────────────────────────────────────────────
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
    """The spec's model reaches the request — not a global environment variable."""
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


# ── tool calling ────────────────────────────────────────────────────────────────────────────────────────
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

    asyncio.run(run())          # does not raise
    assert fired == []          # skips the call with invalid JSON


def test_tool_call_fired_on_early_return(monkeypatch):
    """The consumer breaks the loop (GeneratorExit) → the already accumulated tool call is NOT lost (finally)."""
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
    # audit 2026-07-26: the fallback (config without a model, or broken config.v2) must NEVER fall back to grok — it is
    # BANNED in FlashBrain (misroutes memory→widget_data). Covers both branches: dict without "model" and exception.
    monkeypatch.setattr("config.v2.fast_model_spec",
                        lambda: {"provider": "aimlapi", "model": "", "base_url": "", "api_key": ""})
    assert "grok" not in fc.spec_from_config().model.lower()

    def _boom():
        raise RuntimeError("config rota")
    monkeypatch.setattr("config.v2.fast_model_spec", _boom)
    spec = fc.spec_from_config()
    assert "grok" not in spec.model.lower()
    assert spec.model == fc._FALLBACK_MODEL


# ── V2-171: a dropped action is a FACT, not a `continue` ──────────────────────────────────────────────────
#
# Measured on 2026-08-20 against the actual flagship (deepseek-v4-pro): the turn ran with `max_tokens=200`, and a
# well-written escalation takes ~1000–1400 JSON characters by itself. The provider cut it off with
# `finish_reason="length"`, the arguments arrived incomplete, `json.loads` blew up, and the `except` did a
# `continue`. 67 actions lost across 27 runs, 48 of them escalations that never reached a Brain Worker.
# From the outside, it looked as if zaelar promised and did nothing. It was not lying: the action was discarded.
def _chunk_fr(reason):
    return SimpleNamespace(choices=[SimpleNamespace(delta=_delta(None, None), finish_reason=reason)])


def test_the_cap_fits_the_most_important_tool_call():
    """The limit must fit a COMPLETE escalation. Measured: 972–1408 JSON characters, plus the phrase that
    zaelar says aloud. And raising it costs no latency — also measured, 3 runs per arm: TTFT 0.99s at
    200 and 0.91s at 1200, with the SAME response — because a limit is a ceiling, not a target."""
    from nucleo.flash import fast_client as fc

    assert fc._DEFAULT_MAX_TOKENS >= 1000


def test_the_stream_records_WHY_it_ended(monkeypatch):
    """The fact that turned this into a mystery: without `finish_reason`, a limit cutoff and a clean ending are
    indistinguishable from inside the loop."""
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
    assert fired == []                                   # still not executed: the arguments are not readable
    dropped = m.get("dropped_tool_calls") or []
    assert len(dropped) == 1
    assert dropped[0]["name"] == "escalate_to_slowbrain"
    assert "tope" in dropped[0]["reason"]                 # and says WHY, which was what was missing


def test_and_says_so_where_the_operator_can_see_it(monkeypatch):
    """While the failure lived only in a `logger.warning`, neither the operator, the judge, nor the Master could see it."""
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
    """The sensitivity of everything above: without this, “report dropped calls” and “always report” pass alike."""
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


# ── V2-566: a readable action does not die over a newline, and an unfinished stream is named as one ───────
def test_a_complete_call_with_a_raw_newline_is_salvaged_not_dropped(monkeypatch):
    """A COMPLETE object whose string value carries a literal control character (a class DeepSeek emits) is
    strict-invalid JSON, but the action is perfectly readable. Dropping it turned a newline into a lost errand;
    the salvage is recorded so it can be measured instead of assumed."""
    rec, m = {}, {}
    chunks = [_chunk(tool_calls=[_tool_call(0, name="escalate_to_slowbrain",
                                            args='{"request": "line one\ny line two"}')]),
              _chunk_fr("tool_calls")]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], metrics=m,
                                           on_tool_call=lambda n, a: fired.append((n, a))):
            pass

    asyncio.run(run())
    assert fired == [("escalate_to_slowbrain", {"request": "line one\ny line two"})]
    assert not m.get("dropped_tool_calls")
    assert m.get("salvaged_tool_calls") == ["escalate_to_slowbrain"]


def test_an_unfinished_stream_is_not_blamed_on_the_models_json(monkeypatch):
    """Measured 2026-09-03 (Soria, 16:02:47): the operator barged in mid-escalation, the stream closed with
    no finish_reason, and the half-accumulated arguments were filed as «argumentos ilegibles» — sending the
    diagnosis toward «the model emits broken JSON» when the model was interrupted mid-sentence. Three facts,
    three labels: token cap, unfinished stream, genuinely illegible object."""
    rec, m = {}, {}
    # A clean JSON prefix and then silence: no finish_reason chunk ever arrives (cancelled turn / broken pipe).
    chunks = [_chunk(tool_calls=[_tool_call(0, name="escalate_to_slowbrain",
                                            args='{"request": "Reservar una mesa para comer')])]
    _patch_client(monkeypatch, chunks, rec)
    fired = []

    async def run():
        async for _ in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k"),
                                           tools=[{"type": "function"}], metrics=m,
                                           on_tool_call=lambda n, a: fired.append(n)):
            pass

    asyncio.run(run())
    assert fired == []                                    # still dropped: the action never finished arriving
    dropped = m.get("dropped_tool_calls") or []
    assert len(dropped) == 1
    assert "stream" in dropped[0]["reason"]               # …and the label says the stream was cut,
    assert "ilegible" not in dropped[0]["reason"]         # not that the model wrote unreadable arguments


# ── V2-176 front 2: the dropped action must reach the NEXT TURN ───────────────────────────────────────────
#
# V2-171 left the drop in the turn's metrics and observability — where the operator can look at it
# LATER. But the phrase (“I'll put you through to it”) was already said in that same turn, so the only thing that can
# still be fixed is the following turn… and it saw nothing. The conversation continued as if the order
# had gone out, which is the heart of V2-176: narrating work that did not happen.
#
# Same remedy as `tasks.recently_finished()` (V2-150) and `dispatch._EXPIRED_CONFIRM` (V2-190): a fact that
# lives for only one turn is a fact the conversation loses.
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
    """A fact repeated in every state stops being a fact and becomes noise — and this one has already been said."""
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
    """The sensitivity: without this, “report the drop” and “always report” pass alike."""
    from nucleo.flash import fast_client as fc
    from nucleo.flash import prompt as _p

    fc.clear_drops()
    assert "NO LLEGÓ A EJECUTARSE" not in _p.live_state()
