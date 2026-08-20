"""`thinking: disabled` is not a tuning knob on this leg — without it the leg returns nothing at all.

Measured 2026-08-20 with the judge's real 23.000-character prompt, both models, 3.000 output tokens:

    flash, thinking on  →     0 chars, 21,0 s, out_tok=3000   (all reasoning, EMPTY body)
    flash, disabled     → 4.620 chars, 10,4 s, out_tok=1317
    pro,   thinking on  →     0 chars, 48,7 s, out_tok=3000
    pro,   disabled     → 4.397 chars, 19,7 s, out_tok=1299

So the empty bodies that cost `book-hotel-night-known__es` its fourth and fifth INFRA were not a token budget
problem: the model spent the whole allowance thinking and returned nothing. The engine already knew — its
`provider_chain.py` comment says the broker ACCEPTS the flag and reasons anyway while `api.deepseek.com` OBEYS
it — and this leg simply was not passing it. With the flag, that parked round was judged without re-driving the
conversation: overall 3, after four thrown-away rounds.
"""
from __future__ import annotations

import json

from tests.voice.e2e.agent import llm as L


def _payload_of(monkeypatch) -> dict:
    seen: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()

    def _urlopen(req, timeout=0):
        seen["payload"] = json.loads(req.data.decode())
        seen["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "k", raising=False)
    monkeypatch.setattr(L.urllib.request, "urlopen", _urlopen)
    L.deepseek_direct_call([{"role": "user", "content": "x" * 100}], max_tokens=2000)
    return seen


def test_the_direct_call_disables_thinking(monkeypatch):
    got = _payload_of(monkeypatch)
    assert got["payload"].get("thinking") == {"type": "disabled"}, \
        "sin esto el proveedor gasta todo el presupuesto razonando y devuelve el cuerpo vacío"


def test_it_goes_to_the_VENDOR_endpoint(monkeypatch):
    got = _payload_of(monkeypatch)
    assert "api.deepseek.com" in got["url"]
    assert "aimlapi" not in got["url"], "esta pata existe justamente para no pasar por el broker"


def test_and_carries_no_broker_prefix_in_the_model_name(monkeypatch):
    """The vendor answers to `deepseek-v4-flash`; the broker's `deepseek/…` gets a 404 that reads as an outage."""
    got = _payload_of(monkeypatch)
    assert "/" not in got["payload"]["model"], got["payload"]["model"]
