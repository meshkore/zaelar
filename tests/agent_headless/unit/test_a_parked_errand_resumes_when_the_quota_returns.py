"""The other half of parking an errand for the quota's reset (2026-10-11): when its job comes due, the loop does
not SPEAK the job (it has no reminder text), it relaunches the errand — «The quota is back: I'm picking up …» and
the same goal escalated again. If the chain is still asleep (a reset hour that lied), it parks once more, and past
the cap it says the plain asleep sentence, which promises nothing."""
import asyncio
import time

import pytest

import bus
from memory import db as memdb
from nucleo.pulse import loop as nloop
from nucleo.pulse import scheduler, sparks
from nucleo.workers import providers, quota_wait

GOAL = "Find car and bike events around Los Angeles on October 17-18"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    memdb.reset_db()
    memdb.get_db()
    bus.reset()
    monkeypatch.setattr(quota_wait, "_PARKS", {})
    state = {"until": time.time() + 600, "launched": [], "said": []}
    monkeypatch.setattr(providers, "exhausted_until", lambda: state["until"])
    from nucleo.acts import errand as escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda goal, context=None, **kw: state["launched"].append((goal, context or {})) or 1)
    yield state
    memdb.reset_db()
    bus.reset()


def _fire(state):
    async def deliver(title, text, **kw):
        state["said"].append(text)
    lp = nloop.OrchestratorLoop(spark_gate=sparks.SparkGate(daily_max=0, min_gap_s=0, prob=0.0, clock=lambda: 0.0,
                                                            rng=lambda: 1.0), deliver=deliver, consolidate_every_s=1e9)
    asyncio.run(lp._fire_due(time.time() + 3 * 3600))


def test_quota_back_relaunches_the_same_errand_and_says_so(world):
    assert quota_wait.park(GOAL, {"kind": "research", "sheet": "results::x1"})
    world["until"] = 0.0
    _fire(world)
    assert [g for g, _ in world["launched"]] == [GOAL]
    assert world["launched"][0][1].get("sheet") == "results::x1" and world["launched"][0][1]["src"] == "quota_resume"
    assert len(world["said"]) == 1 and "quota is back" in world["said"][0]
    assert not quota_wait.is_parked(GOAL), "a fired one-time job is closed"


def test_still_asleep_parks_again_without_relaunching(world):
    quota_wait.park(GOAL)
    world["until"] = time.time() + 4 * 3600         # the reset moved
    _fire(world)
    assert world["launched"] == [] and world["said"] == []
    assert quota_wait.is_parked(GOAL)


def test_past_the_cap_it_says_the_plain_asleep_line(world):
    for _ in range(quota_wait.MAX_PARKS - 1):
        quota_wait.park(GOAL)
        quota_wait.forget("")
    quota_wait.park(GOAL)
    world["until"] = time.time() + 4 * 3600
    _fire(world)
    assert world["launched"] == [] and len(world["said"]) == 1
    assert "quota" in world["said"][0] and "pick it up" not in world["said"][0]


def test_an_ordinary_reminder_is_still_spoken(world):
    scheduler.create("drink water", "1m", name="water")
    _fire(world)
    assert world["said"] == ["drink water"] and world["launched"] == []
