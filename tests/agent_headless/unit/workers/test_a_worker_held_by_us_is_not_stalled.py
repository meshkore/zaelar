"""A worker WE froze is not a silent provider: the stall clock waits while its process is held (V2-831 audit A1).

The class: the stall watchdog (V2-645) measures the provider's silence, so time the engine itself held the process
(SIGSTOP) is not silence. V2-747 taught it the operator's ⏻; the resource envelope (T-27) and the self watchdog's shed
(T-28) pause workers too, through the same `session.pause()`, and the clock kept counting them — after the stall budget
the worker was killed as «no answer from the provider» and restarted, adding load to a host that was already short of
memory. One reader now answers «held by us» for every pauser: the backend's own `paused`.
"""
import asyncio

from nucleo.workers import envelope
from nucleo.workers import stall as stall_mod
from nucleo.workers.session import SessionRecord, WorkerSession


class _PausableHangingBackend:
    """One event, then silence; pause/resume behave like the real SIGSTOP/SIGCONT backend."""
    name = "fake"
    alive = True

    def __init__(self):
        self.stopped = False
        self._paused = False

    async def start(self, prompt, *, spec):
        pass

    async def send(self, text):
        pass

    async def events(self):
        yield type("E", (), {"type": "phase", "data": {"label": "starting"}})()
        await asyncio.sleep(3600)

    async def stop(self, *, grace: float = 3.0):
        self.stopped = True
        self.alive = False

    def pause(self) -> bool:
        if self._paused:
            return False
        self._paused = True
        return True

    def resume(self) -> bool:
        if not self._paused:
            return False
        self._paused = False
        return True

    @property
    def paused(self) -> bool:
        return self._paused


def _session(task_id: str, started: float):
    b = _PausableHangingBackend()
    rec = SessionRecord(task_id=task_id, goal="compare three flats", kind="generic")
    s = WorkerSession(b, type("S", (), {"model": "", "kind": "generic"})(), rec)
    rec.session, rec.started, rec.status = s, started, "running"
    return b, rec, s


def _quiet_clocks(monkeypatch):
    monkeypatch.setattr(stall_mod, "_STALL_S", 0.3)
    monkeypatch.setattr(stall_mod, "_TICK_S", 0.02)
    monkeypatch.setattr(stall_mod, "_hibernating", lambda: False)     # the ⏻ is ON: only the envelope pauses


async def _held_then_released(monkeypatch, pauser):
    _quiet_clocks(monkeypatch)
    _, old, _ = _session("old", 1.0)
    b, new, s = _session("new", 2.0)
    run = asyncio.ensure_future(s.run("whatever"))
    await asyncio.sleep(0.05)
    assert pauser([old, new]) and b.paused, "the pauser must have frozen the newest worker"
    await asyncio.sleep(1.0)                                   # > 3× the stall budget, all of it held by us
    held_status, held_stopped = new.status, b.stopped
    b.resume()
    await asyncio.wait_for(run, timeout=3)                     # released: the provider's silence counts again
    return held_status, held_stopped, new.status, b.stopped


def test_a_worker_the_envelope_paused_outlives_the_stall_budget(monkeypatch):
    monkeypatch.setattr(envelope, "measured", lambda: (2_000, 50))              # far under the pause floor
    held_status, held_stopped, end_status, end_stopped = asyncio.run(
        _held_then_released(monkeypatch, lambda recs: envelope.relieve(recs).startswith("paused")))
    assert held_status != "error" and not held_stopped, "a worker frozen by the envelope was killed as stalled"
    assert end_status == "error" and end_stopped, "once resumed, a silent provider must still be caught"


def test_a_worker_paused_by_any_other_door_is_held_too(monkeypatch):
    # Another pauser (the self watchdog's shed, a future one): whoever froze it, the backend says so.
    held_status, held_stopped, *_ = asyncio.run(
        _held_then_released(monkeypatch, lambda recs: recs[-1].session.pause()))
    assert held_status != "error" and not held_stopped


def test_an_unreadable_paused_state_keeps_the_clock(monkeypatch):
    # Fail-OPEN, like the switch: a watchdog that stops watching on any doubt is the failure it exists for.
    _quiet_clocks(monkeypatch)

    async def _go():
        async def _never():
            await asyncio.sleep(3600)
            yield None
        return await stall_mod.bounded_next(_never().__aiter__(), frozen=lambda: 1 / 0)

    assert asyncio.run(asyncio.wait_for(_go(), timeout=3)) == ("stalled", None)
