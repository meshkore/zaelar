"""Provider failover WITHIN a cluster turn (`connectors/meshkore/brain.py`, 2026-08-03).

Before: `make_brain()` fixed the tier ONCE when the server started; with the Z.AI quota exhausted, EVERY turn
(the heartbeat insisting on responding to a peer) repeated the SAME broken call → 429 in a loop, with no failover and no
warning. Now `_brain()` queries `provider_chain.pick()` on every turn and, if the turn fails because of the provider,
it fails over and retries THAT SAME turn once before giving up.
"""
import asyncio

import pytest

from connectors.meshkore import brain
from nucleo.flash import provider_chain as pc

Z_AI = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "env": ["Z_AI_API_KEY"]}
AIMLAPI = {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "model": "", "env": ["AIMLAPI_KEY"]}
REAL_429_EXHAUSTED = ("429 Too Many Requests — {\"error\":{\"message\":"
                      "\"[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-04 00:00:00]\"}}")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # The cooldown state stopped being a MODULE-level dict and became a `CooldownStore` (V2-098), which is what
    # this chain and the workers' chain share. This file continued isolating `pc._store._cooldown`, an attribute that
    # no longer exists, so its three cases had been crashing in `setup` ever since — and this was not visible because
    # **the file was not in the testmap**: `tests run all` did not execute it. It is the V2-158 failure again
    # (2026-08-21). The REAL store is isolated, which is what must be isolated today to avoid touching anyone's
    # `sys_kv`.
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    yield


def test_a_provider_failure_relays_and_retries_the_same_turn(monkeypatch):
    """The turn with z.ai fails with an exhausted-quota 429 → it fails over to aimlapi and the SAME turn is retried
    (the real-time message to the peer is not lost merely because the primary tier is out of quota)."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [Z_AI, AIMLAPI])   # pick()/note_failure() are left REAL: the point
    # of the test is that, after the failure, the real chain recalculates the failover against the cooldown it just recorded.

    calls = []

    async def fake_respond(text, *, spec, **kw):
        calls.append(spec.base_url)
        if spec.base_url == Z_AI["base_url"]:
            raise RuntimeError(REAL_429_EXHAUSTED)
        return "hola desde el relevo"

    monkeypatch.setattr("nucleo.flash.cluster.respond", fake_respond)
    b = brain.make_brain()
    out = asyncio.run(b("hola"))

    assert out == "hola desde el relevo"
    assert calls == [Z_AI["base_url"], AIMLAPI["base_url"]]      # one attempt, one failover, one retry — no more
    assert pc._store._cooldown.get("z.ai", 0) > 0                        # z.ai remains on cooldown (STICKY for the next turn)


def test_a_passing_rate_limit_is_not_relayed(monkeypatch):
    """A bare 429 (without quota text) is a transient rate limit — it does not fail over and is propagated (the bridge
    already logs it, and the heartbeat will retry it later; the provider should not be penalized for this)."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [Z_AI])

    async def fake_respond(text, *, spec, **kw):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr("nucleo.flash.cluster.respond", fake_respond)
    b = brain.make_brain()
    with pytest.raises(RuntimeError):
        asyncio.run(b("hola"))
    assert pc._store._cooldown == {}                                     # a transient blip is not penalized


def test_no_tier_available_raises_before_calling_the_engine(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [])
    monkeypatch.setattr(pc, "pick", lambda *a, **k: None)
    b = brain.make_brain()
    with pytest.raises(RuntimeError):
        asyncio.run(b("hola"))
