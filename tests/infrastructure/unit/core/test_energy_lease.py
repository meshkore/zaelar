"""ENERGY LEASE (ADR-0005) — the ceiling by which the machine watches itself.

What is being tested is not that subtraction subtracts. It is what the design exists to guarantee: that
without a link to the cloud this machine does NOT spend without a ceiling, and that the fuse does not
take control away from the operator.
"""
import time

import pytest
from tests.waiting import until

from nucleo.energy import lease as energy_lease


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    energy_lease._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    yield
    energy_lease._reset_for_tests()


def _con_arriendo(monkeypatch, granted=100.0, ttl=1800.0):
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update({"lease_id": "L1", "granted": granted, "spent": 0.0,
                                "expires_at": time.time() + ttl, "at": time.time()})


def test_self_host_no_tiene_arriendo_ni_lo_necesita(monkeypatch):
    """Without a cloud account: always allowed, zero state, zero network. Anyone who self-hosts pays for
    their own APIs, and nobody leases them energy."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: False)
    assert energy_lease.allowed() is True
    energy_lease.note_spend(999999)
    assert energy_lease.allowed() is True
    assert energy_lease.snapshot() == {"leased": False}


def test_sin_arriendo_una_cuenta_de_nube_NO_puede_gastar(monkeypatch):
    """Fail-closed. The absence of a lease is the CLOSED state, not “go ahead until someone says
    otherwise”—which is the `guarded-until-configured` behavior that cost nine days of open cloud spend."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    assert energy_lease.allowed() is False


def test_un_arriendo_caducado_no_sirve_aunque_le_quede_saldo(monkeypatch):
    """Expiry is the other half of the ceiling: a machine that has slept for months cannot wake up and
    spend against an authorization from another era."""
    _con_arriendo(monkeypatch, ttl=-1)
    assert energy_lease.expired() is True
    assert energy_lease.allowed() is False


# ── EXPIRED IS NOT EXHAUSTED ──────────────────────────────────────────────────────────────────────
# The three below come from a REAL production failure (2026-08-14): the machine spent the night powered
# on without spending, its lease ran out at 17:28, and by morning the agent sat stopped with 1,987
# Energy in the account. No alert, no reason on screen: the operator only saw that it would not start.
# The cause was treating "my clock ran out" the same as "I ran out of energy".

# Captured at IMPORT time, before the autouse fixture swaps `_persist` for a no-op — this is the only
# way to get a handle on the real function from inside a test.
_REAL_PERSIST = energy_lease._persist


def test_the_lease_really_persists_to_sys_kv(monkeypatch):
    """The durable counter is what stops a restart LOOP from being uncapped spend: without it every boot
    puts `spent` back to zero and asks for a fresh lease.

    It was broken in production for a day by a bare `import memory` — that facade is a docstring and
    re-exports nothing, so `memory.kv_get` raised AttributeError, the `except` downgraded it to a debug
    line, and persistence quietly stopped happening. The evidence was in the cloud, not in any test:
    seven consecutive leases, every one `reported_spent = 0`.

    `_persist` swallows everything on purpose (saving must never break a turn), so asserting "it did not
    raise" proves nothing at all. The only assertion worth making is that the write LANDED.
    """
    from memory import api as memapi
    written = {}
    monkeypatch.setattr(memapi, "kv_set", lambda k, v: written.update({k: v}))
    energy_lease._state.update({"lease_id": "L1", "granted": 100.0, "spent": 3.0})
    _REAL_PERSIST()
    assert energy_lease._KV_KEY in written, "the lease never reached sys_kv: a restart would forget it"
    assert written[energy_lease._KV_KEY]["spent"] == 3.0


def test_a_spend_metered_in_a_worker_thread_still_asks_for_the_renewal(monkeypatch):
    """A spend metered inside `asyncio.to_thread` has no running loop. The renewal used to be dropped there, so a
    long background job spent the lease to zero without ever asking, and the fuse stopped an account that still
    had 200 Energy. The renewal must reach the server's loop."""
    import asyncio
    import threading
    from nucleo.energy import meter as energy_meter
    _con_arriendo(monkeypatch)
    asked = []

    async def fake_ensure(*, reason="boot", force=False):
        asked.append(reason)
        return True
    monkeypatch.setattr(energy_lease, "ensure", fake_ensure)

    async def main():
        monkeypatch.setattr(energy_meter, "_loop", asyncio.get_running_loop())
        t = threading.Thread(target=energy_lease.note_spend, args=(60.0,))
        t.start()
        await asyncio.to_thread(t.join)
        await until(lambda: asked, "a renewal asked from a worker thread", timeout_s=2)
    asyncio.run(main())
    assert asked == ["half_spent"], "a spend from a worker thread never asked for a renewal"
