"""A reasoning model charges its thinking against `max_tokens`, so the brief never fit — and said nothing.

Measured 2026-08-27 against the live reasoning tier (Z.AI GLM through its Anthropic-compatible gateway), on the
composer's real prompt:

    thinking ON  · 1.600 tokens →  truncated, `parse()` → None   (logged «respuesta ilegible»)
    thinking ON  · 8.000 tokens →  parseable, but 67,7 s and 2.517 output tokens
    thinking OFF · 1.600 tokens →  parseable in 22,3 s and 681 output tokens

The failure had the shape of a broken model and was really a budget that never fit: HTTP 200, no error field
anywhere, an empty or half-written JSON, and a worker leaving WITHOUT a brief — an undirected search that still
looks like a search. The seconds belong to the person, who cannot see anything until the worker starts.

These tests pin the two halves: the transport must be ABLE to say "answer, don't deliberate", and the composer
must actually SAY it. Either one alone is green while the defect is fully alive.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.llm.fast_client import FastClient, ModelSpec


class _Captured(Exception):
    """Stops the call once the payload exists — we are testing what is SENT, not what comes back."""

    def __init__(self, payload):
        self.payload = payload


def _zai_spec() -> ModelSpec:
    return ModelSpec(model="glm-4.6", base_url="https://api.z.ai/api/anthropic", api_key="k")


def _payload_sent(monkeypatch, **kwargs) -> dict:
    seen = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"content": [{"type": "text", "text": "{}"}]}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            seen.update(json or {})
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    asyncio.run(FastClient().complete([{"role": "user", "content": "hola"}], spec=_zai_spec(),
                                      max_tokens=1600, **kwargs))
    return seen


def test_the_transport_can_be_told_to_skip_the_deliberation(monkeypatch):
    assert _payload_sent(monkeypatch, no_thinking=True).get("thinking") == {"type": "disabled"}


def test_and_says_nothing_when_nobody_asks(monkeypatch):
    """Sensitivity: every other caller must be byte-identical to before — thinking stays ON by default."""
    assert "thinking" not in _payload_sent(monkeypatch)


def test_zai_is_declared_blind_because_it_was_measured_blind():
    """Not a preference — a fact about the endpoint, and the reason `ZAELAR_NAV_VISION=0` reaches the browser.

    Measured 2026-08-27: a flat red PNG came back «Orange», a flat blue one «Teal», and a white image with
    «ZAELAR 4271» on it was described as a CAPTCHA grid of crosswalks. Confabulation, not refusal — which is
    worse than DeepSeek's honest «I cannot read the screenshot», because it has the shape of an observation.
    Flipping this flag back requires measuring again, not reading the provider's page.
    """
    from nucleo.workers import providers

    zai = next(k for k in providers.KNOWN if k["name"] == "z.ai")
    assert zai.get("vision") is False
    assert providers.vision_env(zai) == {"ZAELAR_NAV_VISION": "0"}


def _openai_kwargs_sent(monkeypatch, spec) -> dict:
    seen = {}

    class _Completions:
        async def create(self, **kw):
            seen.update(kw)
            raise _Captured(kw)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(FastClient, "_client_for", lambda self, s: _Client())
    with pytest.raises(_Captured):
        asyncio.run(FastClient().complete([{"role": "user", "content": "hola"}], spec=spec, max_tokens=1600,
                                          no_thinking=True))
    return seen


def test_an_endpoint_that_rejects_the_field_never_gets_it(monkeypatch):
    """Measured 2026-10-22: the composer's relay to OpenAI answered «Unrecognized request argument supplied:
    thinking» (400) every time — the brief was lost and a healthy tier went on cooldown."""
    sent = _openai_kwargs_sent(monkeypatch, ModelSpec(model="gpt-4.1-mini", base_url="https://api.openai.com/v1",
                                                      api_key="k"))
    assert "thinking" not in (sent.get("extra_body") or {})


def test_an_endpoint_that_obeys_it_still_gets_it(monkeypatch):
    sent = _openai_kwargs_sent(monkeypatch, ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com",
                                                      api_key="k"))
    assert sent["extra_body"]["thinking"] == {"type": "disabled"}
