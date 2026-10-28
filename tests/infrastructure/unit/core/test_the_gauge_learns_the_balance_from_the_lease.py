"""The Energy gauge learns the balance from the LEASE answer, and goes down with the lease's local spend.

The gauge used to learn the balance only from usage-report responses. Under the lease a Machine does not report each
charge, so it never learned it: an account with 397 Energy showed an unlit gauge. The lease answer carries the
balance and, when the cloud sends them, the plan's gauge facts (`cycle_energy`, `scale`, `tier`), which make the
gauge «the cycle's Energy minus what was spent».
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.energy import lease as energy_lease, meter as energy_meter


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    energy_lease._reset_for_tests()
    energy_meter._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    monkeypatch.setattr(energy_meter, "enabled", lambda: True)
    monkeypatch.setattr(energy_meter, "_load_once", lambda: None)
    yield
    energy_lease._reset_for_tests()
    energy_meter._reset_for_tests()


def _lease_answer(monkeypatch, body):
    import httpx

    class _R:
        status_code = 200

        def json(self):
            return body

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _C)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.example.test")


def test_a_lease_answer_tells_the_gauge_the_balance_and_the_cycle(monkeypatch):
    _lease_answer(monkeypatch, {"ok": True, "lease_id": "L1", "energy": 40, "ttl_s": 1800, "balance": 397,
                                "plan": {"key": "free", "name": "Free", "cycle_energy": 500, "scale": 13000, "tier": 0}})
    assert asyncio.run(energy_lease.ensure(reason="boot", force=True))
    snap = energy_meter.snapshot()
    assert snap["known"] and snap["balance"] == 397 and snap["capacity"] == 500
    assert snap["plan"] == {"key": "free", "name": "Free", "tier": 0, "scale": 13000}


def test_the_gauge_goes_down_with_the_local_spend(monkeypatch):
    _lease_answer(monkeypatch, {"ok": True, "lease_id": "L1", "energy": 40, "ttl_s": 1800, "balance": 397,
                                "plan": {"name": "Free", "cycle_energy": 500}})
    asyncio.run(energy_lease.ensure(reason="boot", force=True))
    energy_lease.note_spend(7)
    assert energy_meter.snapshot()["balance"] == pytest.approx(390)


def test_a_refused_lease_still_tells_the_balance(monkeypatch):
    _lease_answer(monkeypatch, {"ok": False, "error": "plan_expired", "balance": 0, "plan": {"name": "Free"}})
    assert not asyncio.run(energy_lease.ensure(reason="boot", force=True))
    snap = energy_meter.snapshot()
    assert snap["known"] and snap["balance"] == 0


def test_without_gauge_facts_the_capacity_is_the_highest_balance_seen():
    energy_lease._gauge_from_lease({"balance": 800})
    energy_lease._gauge_from_lease({"balance": 600})
    assert energy_meter.snapshot()["capacity"] == 800


def test_a_machine_booting_on_a_persisted_lease_still_asks_when_the_gauge_knows_nothing(monkeypatch):
    """Only a lease ANSWER tells the gauge the balance: booting on a still-valid lease must not leave it unlit."""
    asked = []
    _lease_answer(monkeypatch, {"ok": True, "lease_id": "L2", "energy": 40, "ttl_s": 1800, "balance": 397})
    energy_lease._state.update({"lease_id": "L1", "granted": 40.0, "spent": 1.0,
                                "expires_at": __import__("time").time() + 1500})
    real = energy_lease._request

    async def counting(reason):
        asked.append(reason)
        return await real(reason)
    monkeypatch.setattr(energy_lease, "_request", counting)
    asyncio.run(energy_lease.ensure(reason="boot"))
    assert asked == ["boot"] and energy_meter.snapshot()["balance"] == 397
    asyncio.run(energy_lease.ensure(reason="boot"))
    assert asked == ["boot"], "once the gauge knows, a valid lease is not asked for again"


def test_the_gauge_state_survives_a_restart(monkeypatch):
    """`kv_set` encodes JSON itself; the state was stored as an already-encoded string, so it came back as a string
    and a restarted engine never restored it."""
    stored = {}
    from memory import api as memory
    monkeypatch.setattr(memory, "kv_set", lambda k, v: stored.__setitem__(k, v))
    energy_lease._gauge_from_lease({"balance": 397, "plan": {"name": "Free", "cycle_energy": 500}})
    assert isinstance(stored[energy_meter._KV_KEY], dict)
    assert stored[energy_meter._KV_KEY]["balance"] == 397 and stored[energy_meter._KV_KEY]["capacity"] == 500
