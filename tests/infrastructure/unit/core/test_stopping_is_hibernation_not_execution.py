"""V2-747 — ⏻ OFF freezes the work; it does not spend and it does not kill.

## The operator's rule

> «Si hay un proceso en marcha y yo apago el sistema, veo que el proceso sigue funcionando. Sería ideal
>  pausar esos procesos y dejarlos parados… si el agente está vivo y el pulso está activo, me parece bien
>  que funcionen los brain workers. Pero **si he decidido pararlo para que no gaste tokens, para que no
>  haga nada, el sistema se tiene que paralizar. No borrar ni detener, sino sería algo así como una
>  hibernación.**»

`runstate` was already built for exactly that (SIGSTOP, reversible, the observability session closed). Two
things outlived it, and they are opposite failures — one kept SPENDING, the other KILLED.

## Measured, in his own database, after `run stop` at 20:13:20

| t | what happened with the agent stopped |
|---|---|
| 20:14:15 | `trace pulso · [cluster:commons · heartbeat]` — a full brain turn |
| 20:15:55 | …again |
| 20:17:35 | …again |
| **20:18:20** | `task stalled — sin respuesta del proveedor en 5 min, aborto la tarea` |
| 20:18:21 | 🔔 a notification to him, about a task the engine had killed itself |
| 20:19:15 · 20:20:55 · 20:22:35 | the pulse, still going when the database was read |

`connectors/meshkore/bridge.py` had no reference to `runstate` at all — the one connector that spends a
model call on its own initiative. And `nucleo/workers/stall.py` counted frozen time as provider silence:
the freeze that was supposed to PRESERVE the job is what made the watchdog abort it, five minutes later
to the second.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from nucleo.workers import stall


# ── the clock does not run while the work is frozen ───────────────────────────────────────────────────

class _Silent:
    """A backend stream that never yields — a SIGSTOPped worker, from the server's side."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)


def _drive(frozen_for_ticks: int, stall_s: float, tick_s: float):
    """Run `bounded_next` against silence, with the switch OFF for the first N ticks. Returns the verdict
    and how many ticks elapsed — the clock is the number of `asyncio.wait` timeouts, not wall time."""
    ticks = {"n": 0}
    real_wait = asyncio.wait

    async def _wait(aws, timeout=None):
        ticks["n"] += 1
        return await real_wait(aws, timeout=0)          # every slice expires instantly

    async def _run(monkey):
        return await stall.bounded_next(_Silent().__aiter__())

    class _M:
        pass

    import unittest.mock as _mock
    with _mock.patch.object(stall.asyncio, "wait", _wait), \
         _mock.patch.object(stall, "_STALL_S", stall_s), \
         _mock.patch.object(stall, "_TICK_S", tick_s), \
         _mock.patch.object(stall, "_hibernating", lambda: ticks["n"] <= frozen_for_ticks):
        verdict, _ = asyncio.run(_run(None))
    return verdict, ticks["n"]


def test_a_provider_that_really_went_quiet_is_still_aborted():
    """The watchdog V2-645 built has to keep working — this narrows WHEN it counts, never WHETHER."""
    verdict, ticks = _drive(frozen_for_ticks=0, stall_s=20.0, tick_s=5.0)
    assert verdict == "stalled"
    assert ticks == 4, f"20 s at 5 s a slice is four slices, not {ticks}"


def test_the_five_minutes_do_not_run_while_the_agent_is_stopped():
    """THE MEASURED BUG: he pressed ⏻ and five minutes later the engine aborted his job. Frozen time is
    ours, not the provider's — a process that cannot emit is not a provider that will not."""
    verdict, ticks = _drive(frozen_for_ticks=100, stall_s=20.0, tick_s=5.0)
    assert verdict == "stalled"
    assert ticks == 104, (
        "the clock counted the frozen slices: hibernation became a five-minute execution")


def test_the_read_is_issued_ONCE_and_not_re_issued_per_slice():
    """`wait_for` CANCELS what it times out on, so a slice loop built on it would drop whatever the
    provider sent during the slice that expired. The bound is a wait, never a retry."""
    src = inspect.getsource(stall.bounded_next)
    body = src.split('"""', 2)[-1]                      # the code, not the note that explains it
    assert "asyncio.ensure_future(it.__anext__())" in body
    assert "wait_for" not in body, "one `__anext__` per call, waited on in slices"
    assert body.count("__anext__") == 1, "a second read is a retry, and a retry loses the first one"


def test_an_unreadable_switch_keeps_the_watchdog_watching():
    """Fail-OPEN, the direction V2-645 chose: a watchdog that stops watching on any doubt is the failure
    it exists for."""
    import unittest.mock as _mock
    with _mock.patch.dict("sys.modules", {"nucleo.runstate": None}):
        assert stall._hibernating() is False


def test_it_asks_the_ONE_switch_and_does_not_keep_its_own_idea_of_stopped():
    src = inspect.getsource(stall._hibernating)
    assert "runstate.stopped()" in src, (
        "a second source of «is the agent stopped» is how the two come to disagree — `runstate` is the one")


# ── the pulse does not spend while the agent is stopped ───────────────────────────────────────────────

def test_the_cluster_pulse_reads_the_switch_before_deciding_anything():
    from connectors.meshkore import bridge
    src = inspect.getsource(bridge.Bridge._heartbeat if hasattr(bridge, "Bridge") else bridge)
    assert "_agent_stopped()" in src, (
        "the heartbeat fired a full brain turn every 100 s with the agent stopped — six of them measured, "
        "sessionless, and still going when the database was read")
    body = inspect.getsource(bridge)
    i = body.index("async def _heartbeat(self):")
    head = body[i:i + 400]
    assert head.index("_agent_stopped()") < head.index("self._now()"), (
        "the switch is read BEFORE any per-cluster work: gating after the loop body is not gating")


def test_an_INBOUND_peer_message_is_not_gated_by_the_switch():
    """Only SELF-STARTED work hibernates. Dropping what a peer sent us would lose it, and losing a message
    is not hibernating — the asymmetry is deliberate and this is where it is written down."""
    from connectors.meshkore import bridge
    src = inspect.getsource(bridge)
    n = src.count("_agent_stopped()")
    assert n == 2, (
        f"_agent_stopped() appears {n} times: it belongs in the heartbeat loop and its own definition, "
        "and nowhere on the path an inbound message takes")
