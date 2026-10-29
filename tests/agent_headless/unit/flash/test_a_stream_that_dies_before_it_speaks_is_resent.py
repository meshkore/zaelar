"""A reply whose body dies BEFORE it says anything is re-sent like a refused connection (V2-831 T-19 R3b).

Demo pass on a sandbox at build 86, INIT «Remember: Laura…»: DeepSeek answered `200 OK`, then the body died with
`httpx.ReadError()` 545 ms later and the turn failed — no retry, no relay. The connect-phase retry and the
failover covered only `create()`, and `_is_transient` read the exception's NAME and TEXT, which for a bare
`ReadError()` match nothing.

Class: until a chunk carries text, a tool call or a finish, nothing has been emitted, so a transient failure
there is a connect failure — same retry budget, then the same relay. Once something is out, never replay.

Disarms: no held head → the before-the-first-token and budget cases go red; `_says` always False (hold past
speech) → the after-the-first-token case goes red; `_is_transient` without the type check → the by-type cases red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from nucleo.llm import fast_client as fc
from nucleo.llm.fast_client import FastClient, ModelSpec


def _chunk(content=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None),
                                                    finish_reason=finish)])


class _Body:
    """One HTTP body: yields its chunks, then raises `die` (if any) where the script says."""
    def __init__(self, script):
        self.script = script

    def __aiter__(self):
        async def gen():
            for item in self.script:
                if isinstance(item, BaseException):
                    raise item
                yield item
        return gen()


class _Client:
    def __init__(self, bodies):
        self.bodies, self.calls = list(bodies), 0
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kw):
        self.calls += 1
        return _Body(self.bodies.pop(0))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(fc, "_CONNECT_RETRIES", 2)
    monkeypatch.setattr(fc, "_RETRY_BACKOFF_S", 0.0)
    monkeypatch.setattr(fc, "relay_spec_for", lambda spec, role: None)   # no ladder: the retry alone is measured


def _run(monkeypatch, bodies):
    cli = _Client(bodies)
    monkeypatch.setattr(FastClient, "_client_for", lambda self, spec: cli)

    async def go():
        out = []
        async for t in FastClient().stream([{"role": "user", "content": "x"}], spec=ModelSpec(model="m", api_key="k")):
            out.append(t)
        return out
    return cli, go


def test_a_body_that_dies_before_its_first_token_is_resent_and_spoken_once(monkeypatch):
    # the role-only head chunk says nothing; the body dies after it — exactly a 200 whose stream broke
    cli, go = _run(monkeypatch, [[_chunk(""), httpx.ReadError("")], [_chunk("Got it"), _chunk(" — noted.")]])
    assert asyncio.run(go()) == ["Got it", " — noted."], "the reply was not delivered once, whole"
    assert cli.calls == 2, f"expected one re-send, saw {cli.calls} calls"


def test_a_body_that_dies_after_speaking_is_not_replayed(monkeypatch):
    cli, _go = _run(monkeypatch, [[_chunk("Got it"), httpx.ReadError("")], [_chunk("Got it"), _chunk(" again")]])
    seen: list[str] = []

    async def drive():                      # the words heard before the failure must stay visible
        try:
            async for t in FastClient().stream([{"role": "user", "content": "x"}],
                                               spec=ModelSpec(model="m", api_key="k")):
                seen.append(t)
        except httpx.ReadError:
            return "failed"
        return "finished"
    assert asyncio.run(drive()) == "failed", "a stream that had already spoken was retried instead of failing"
    assert seen == ["Got it"], f"speech was replayed: {seen}"
    assert cli.calls == 1


def test_the_retry_budget_bounds_it(monkeypatch):
    dead = [_chunk(""), httpx.RemoteProtocolError("")]
    cli, go = _run(monkeypatch, [list(dead) for _ in range(5)])
    with pytest.raises(httpx.RemoteProtocolError):
        asyncio.run(go())
    assert cli.calls == 1 + fc._CONNECT_RETRIES, cli.calls


@pytest.mark.parametrize("exc", [httpx.ReadError(""), httpx.RemoteProtocolError(""), httpx.ConnectError(""),
                                 httpx.ReadTimeout(""), ConnectionResetError(), TimeoutError()])
def test_a_transport_error_is_transient_by_type_with_no_message(exc):
    assert fc._is_transient(exc), f"{type(exc).__name__}() with no message is not seen as transient"


def test_a_request_error_is_still_not_transient():
    assert not fc._is_transient(ValueError("bad input schema"))
    assert not fc._is_transient(type("E", (Exception,), {"status_code": 400})())


def test_when_the_budget_is_spent_the_same_request_goes_to_the_relay(monkeypatch):
    relay = ModelSpec(model="stand-in", base_url="https://api.openai.com/v1", api_key="k2", provider="openai")
    dead = [_chunk(""), httpx.ReadError("")]
    cli, _go = _run(monkeypatch, [list(dead) for _ in range(1 + fc._CONNECT_RETRIES)] + [[_chunk("Noted.")]])
    monkeypatch.setattr(fc, "relay_spec_for", lambda spec, role: relay if spec.model == "m" else None)
    m: dict = {}

    async def go():
        return [t async for t in FastClient().stream([{"role": "user", "content": "x"}],
                                                     spec=ModelSpec(model="m", api_key="k"), metrics=m)]
    assert asyncio.run(go()) == ["Noted."]
    assert m.get("relayed_to") == "stand-in", m
    assert cli.calls == 2 + fc._CONNECT_RETRIES
