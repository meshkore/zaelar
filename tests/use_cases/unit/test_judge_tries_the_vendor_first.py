"""The judge tries DeepSeek's OWN endpoint before the broker, and that order cost three rounds to learn.

2026-08-20: Z.AI's weekly limit was exhausted, so the judge fell straight to the AIMLAPI broker — which answered
429/503/504 all afternoon. `book-hotel-night-known__es` lost THREE complete eight-minute conversations to a
missing verdict, the third one with the retry visibly firing and all three attempts eating a 504. Through those
same runs the engine was reaching api.deepseek.com without a hiccup: the leg that was missing was the direct one,
which the operator's provider order (direct → broker → last resort) had put first all along.

The subtle half is the model name: the broker catalogues `deepseek/deepseek-v4-flash` and the vendor answers to
`deepseek-v4-flash`. Sending the prefixed name to the vendor returns a 404 that looks exactly like an outage —
the same trap that made a stale `qwen2.5:3b` config look like a dead model on the engine side the same day.
"""
from __future__ import annotations

import pytest

from tests.voice.e2e.agent import llm as L


@pytest.fixture(autouse=True)
def _no_zai_no_sleep(monkeypatch):
    monkeypatch.setattr(L.config, "JUDGE_PROVIDER", "deepseek", raising=False)
    monkeypatch.setattr(L.config, "ZAI_KEY", "", raising=False)
    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "k", raising=False)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_the_vendor_is_tried_before_the_broker(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(L, "deepseek_direct_call",
                        lambda *a, **k: order.append("vendor") or '{"ok":true}')
    monkeypatch.setattr(L, "call", lambda *a, **k: order.append("broker") or "{}")
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["vendor"], "el broker no debería llegar a llamarse si el proveedor directo responde"
    assert txt == '{"ok":true}'
    assert model == L.config.DEEPSEEK_JUDGE_MODEL


def test_the_broker_still_catches_it_when_the_vendor_is_down(monkeypatch):
    """The chain must not become a single point of failure in the other direction."""
    order: list[str] = []

    def _vendor(*a, **k):
        order.append("vendor")
        raise RuntimeError("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(L, "deepseek_direct_call", _vendor)
    monkeypatch.setattr(L, "call", lambda *a, **k: order.append("broker") or "{}")
    L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["vendor", "broker"]


def test_with_no_direct_key_the_chain_is_unchanged(monkeypatch):
    """Sensitivity: a machine without the vendor key must behave exactly as before, not lose a leg."""
    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "", raising=False)
    called: list[str] = []
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: called.append("vendor") or "{}")
    monkeypatch.setattr(L, "call", lambda *a, **k: called.append("broker") or "{}")
    L.judge_call([{"role": "user", "content": "x"}])
    assert called == ["broker"]


def test_the_vendor_model_name_carries_no_broker_prefix():
    """`deepseek/…` is the broker's catalogue name. Sent to the vendor it 404s, and a 404 reads as an outage."""
    assert "/" not in L.config.DEEPSEEK_JUDGE_MODEL, L.config.DEEPSEEK_JUDGE_MODEL
    assert "/" in L.config.JUDGE_MODEL, "el nombre del broker sí lleva prefijo; si no, no es el del broker"


def test_no_key_no_call(monkeypatch):
    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK"):
        L.deepseek_direct_call([{"role": "user", "content": "x"}])
