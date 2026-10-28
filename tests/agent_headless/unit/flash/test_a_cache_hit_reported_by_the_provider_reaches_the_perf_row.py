"""A prefix-cache hit reported by the provider reaches the turn's perf row and the meter (2026-10-14).

Every perf row of the use-case sandboxes said `cache_hit_tokens: null` with `usage_source: provider`: DeepSeek
reported `prompt_cache_hit_tokens`, `fast_client.stream()` stored it in the turn's metrics, and the old text
channel then copied an ALLOWLIST of those metrics into `timings` that did not name it. Since refactor2710-01 there
is one turn (the voice turn), which copies it explicitly into its perf row (`turn_after._reply_extra`).

The chain pinned here, end to end with a fake usage chunk: provider usage → metrics → timings → verdict, plus
the meter receiving the hit exactly once (it is INSIDE `prompt_tokens`, so it is discounted, never added).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import fast_client as fc
from nucleo.flash import turn_perf


class _Delta:
    def __init__(self, content=None):
        self.content = content
        self.tool_calls = None


class _Choice:
    def __init__(self, content=None):
        self.delta = _Delta(content)
        self.finish_reason = None


class _Chunk:
    def __init__(self, content=None, usage=None):
        self.choices = [_Choice(content)]
        self.usage = usage


class _Details:
    def __init__(self, cached):
        self.cached_tokens = cached


class _Usage:
    def __init__(self, p, c, hit=None, details=None):
        self.prompt_tokens, self.completion_tokens, self.total_tokens = p, c, p + c
        if hit is not None:
            self.prompt_cache_hit_tokens = hit
        self.prompt_tokens_details = details


class _Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c


@pytest.fixture
def meter(monkeypatch):
    calls: list[dict] = []
    import nucleo.energy_meter as em
    monkeypatch.setattr(em, "report_llm_usage", lambda **kw: calls.append(kw))
    return calls


def _run(monkeypatch, usage) -> dict:
    stream = _Stream([_Chunk("Hecho."), _Chunk(None, usage=usage)])

    class _Completions:
        async def create(self, **kw):
            return stream

    class _Client:
        class chat:  # noqa: N801
            completions = _Completions()

    monkeypatch.setattr(fc.FastClient, "_client_for", lambda self, spec: _Client())
    spec = fc.ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="test",
                        provider="deepseek")

    async def go():
        m: dict = {}
        async for _ in fc.FastClient().stream([{"role": "system", "content": "x" * 4000},
                                               {"role": "user", "content": "hola"}], spec=spec, metrics=m):
            pass
        return m

    return asyncio.run(go())


@pytest.mark.parametrize("usage", [_Usage(10000, 20, hit=9000), _Usage(10000, 20, details=_Details(9000))],
                         ids=["deepseek_field", "openai_details_fallback"])
def test_a_cache_hit_from_the_usage_chunk_reaches_the_perf_row_and_the_meter_once(monkeypatch, meter, usage):
    metrics = _run(monkeypatch, usage)
    assert metrics.get("prompt_cache_hit_tokens") == 9000, metrics

    timings = {"total_ms": 1500, "ttft_ms": 900, "prompt_tokens": metrics.get("prompt_tokens"),
               "prompt_cache_hit_tokens": metrics.get("prompt_cache_hit_tokens")}
    v = turn_perf.verdict(timings)
    assert v["cache_hit_tokens"] == 9000, ("the turn dropped the provider's cache hit between the stream "
                                           f"metrics and the perf row: {v}")
    assert v["cache_hit_frac"] == 0.9

    assert len(meter) == 1, f"the meter must be called once per stream, got {meter}"
    assert meter[0]["cache_hit_tokens"] == 9000 and meter[0]["prompt_tokens"] == 10000


def test_the_turns_perf_row_copies_the_cache_hit():
    """The one turn copies the provider's hit from its stream metrics into the perf row the verdict reads."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/turn_after.py").read_text(encoding="utf-8")
    assert '"prompt_cache_hit_tokens": llm_metrics.get("prompt_cache_hit_tokens")' in src
