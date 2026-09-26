"""A worker that repeats ONE step without progress is told to deliver, then stopped (demo run, 2026-09-26).

«Find a five-day period during her vacation when my calendar is clear» → a Brain Worker (glm-5.3) computed the
answer, hit the permission gate writing its sheet, and then ran `true` again and again for 15+ minutes. Every
step was an event, so the silence watchdog never fired; it held one of the two pool slots and delivered nothing.
"""
import asyncio
import pathlib
import re

from nucleo.workers import stall


class _FakeBackend:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def _session():
    from nucleo.workers import session as S
    s = S.WorkerSession.__new__(S.WorkerSession)
    s._perm_hits = 0
    s._spin, s._spin_dead = {}, False
    s._b = _FakeBackend()
    s._rec = S.SessionRecord(task_id="7", goal="five free days", kind="web")
    s._emit_chip = lambda *a, **k: None
    s._touch = lambda *a, **k: None
    s._bus = lambda *a, **k: None
    s._emit_step = lambda *a, **k: None
    return s


def _step(s, target):
    from nucleo.workers.base import WorkerEvent
    s._on_event(WorkerEvent(task_id="7", type="step", data={"where": "", "action": "ejecuta", "target": target}))


def test_the_same_step_is_warned_once_then_stopped():
    async def go():
        s = _session()
        for _ in range(stall.SPIN_WARN):
            _step(s, "true")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(s._b.sent) == 1 and "Entrega AHORA" in s._b.sent[0] and "true" in s._b.sent[0]
        for _ in range(stall.SPIN_KILL - stall.SPIN_WARN - 1):
            _step(s, "true")
        assert not s._spin_dead, "one short of the cap it still runs"
        _step(s, "true")
        assert s._spin_dead
        await asyncio.sleep(0)
        assert len(s._b.sent) == 1, "the warning is said once"
    asyncio.run(go())


def test_real_progress_never_counts_as_a_spin():
    s = _session()
    for i in range(3 * stall.SPIN_KILL):
        _step(s, f"navega https://example.com/page/{i % 7}")
    assert not s._spin_dead
    s2 = _session()
    for i in range(3 * stall.SPIN_KILL):
        _step(s2, "true" if i % 2 else "ls")
    assert not s2._spin_dead, "only CONSECUTIVE identical steps count"


def test_the_ending_is_honest():
    from nucleo.workers import session as S
    rec = S.SessionRecord(task_id="7", goal="x", kind="web")
    stall.mark_spinning(rec, lambda *a, **k: None, 20)
    assert rec.status == "error" and rec.ok is False and rec.result_summary


def test_the_run_loop_stops_a_spinning_worker():
    src = (pathlib.Path(__file__).resolve().parents[4] / "nucleo/workers/session.py").read_text("utf-8")
    assert re.search(r"self\._on_event\(ev\)\n\s+if self\._spin_dead:\n\s+_stall\.mark_spinning\(rec, "
                     r"self\._emit_chip, self\._spin\.get\(\"n\", 0\)\)\n\s+try:\n\s+await self\._b\.stop", src)
