"""Background work can never starve the voice (V2-831 T-27).

The operator's cloud host (1 vCPU / 2 GB, no swap): free memory fell 1275 MB -> 0 while two errands ran, was not
given back when they ended, the VAD fell behind real time and the host froze. The envelope, as mechanism plus data
(`config/resources.default.json`, ratios of what the host measures):
  · an errand's process GROUP is reaped when it ends, even when its leader already exited;
  · a new worker is admitted only above the free-memory floor;
  · the admission wait is a CLOCK (`admit_wait_s`): past it the worker starts anyway, said and at lower priority;
  · under pressure the NEWEST worker is paused — only while another runs — and resumed with room again, never one
    the operator paused;
  · a worker runs below the voice's scheduling priority.

Disarms: restore the leader-only early return in `stop` → the reaping test reds; make `admits` always True → the
admission test reds; drop the `paused_by` mark → the resume test reds.
"""
from __future__ import annotations

import asyncio
import os
import signal
from types import SimpleNamespace

import pytest

from nucleo.workers import envelope

GB = 1024 ** 3


def _alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def test_an_errand_leaves_nothing_of_its_group_behind():
    from nucleo.workers.providers.claude import ClaudeCodeSession

    async def run():
        p = await asyncio.create_subprocess_exec("sh", "-c", "sleep 30 & exit 0", start_new_session=True,
                                                 stdin=asyncio.subprocess.PIPE)
        await p.wait()                                    # the leader is gone; its child still holds the group
        assert _alive(p.pid), "the setup did not leave a child in the group"
        s = ClaudeCodeSession()
        s._proc, s._stdin_closed = p, False
        await s.stop(grace=0.2)
        await asyncio.sleep(0.2)
        return p.pid
    pgid = asyncio.run(run())
    assert not _alive(pgid), "the errand ended and a process of its group is still alive"


def test_a_new_worker_waits_below_the_floor_and_starts_with_room(monkeypatch):
    pol = {"worker_nice": 10, "admit_free_ratio": 0.2, "pause_free_ratio": 0.1, "admit_wait_s": 60}
    monkeypatch.setattr(envelope, "policy", lambda: pol)
    assert not envelope.admits(2 * GB, int(0.15 * 2 * GB))
    assert envelope.admits(2 * GB, int(0.25 * 2 * GB))
    readings = iter([(2 * GB, int(0.05 * 2 * GB)), (2 * GB, int(0.05 * 2 * GB)), (2 * GB, int(0.5 * 2 * GB))])
    monkeypatch.setattr(envelope, "measured", lambda: next(readings))
    said = []
    assert asyncio.run(envelope.wait_for_room(lambda: said.append(1), poll_s=0.01)) is True
    assert said == [1], "the wait was not said once"


class _Sess:
    def __init__(self, rec):
        self.rec = rec

    def pause(self):
        self.rec.paused = True
        return True

    def resume(self):
        self.rec.paused = False
        return True


def _rec(tid, started, paused=False):
    r = SimpleNamespace(task_id=tid, status="running", started=started, paused=paused)
    r.session = _Sess(r)
    return r


def test_past_the_deadline_the_worker_starts_anyway_and_says_so(monkeypatch):
    """A busy host must never mean «no worker ever starts»: the wait is a CLOCK from data, then it starts."""
    monkeypatch.setattr(envelope, "policy", lambda: {"worker_nice": 10, "admit_free_ratio": 0.2,
                                                     "pause_free_ratio": 0.1, "admit_wait_s": 0.05})
    monkeypatch.setattr(envelope, "measured", lambda: (2 * GB, int(0.01 * 2 * GB)))   # never any room
    late = []
    import time as _t
    t0 = _t.monotonic()
    assert asyncio.run(envelope.wait_for_room(lambda: None, lambda: late.append(1), poll_s=0.01)) is False
    assert late == [1] and _t.monotonic() - t0 < 2.0, "the deadline did not end the wait"


def test_the_only_running_worker_is_never_paused(monkeypatch):
    """The one errand he is waiting on is never the one frozen: pressure pauses the newest only while another runs."""
    monkeypatch.setattr(envelope, "policy", lambda: {"worker_nice": 10, "admit_free_ratio": 0.2,
                                                     "pause_free_ratio": 0.1, "admit_wait_s": 60})
    monkeypatch.setattr(envelope, "measured", lambda: (2 * GB, int(0.01 * 2 * GB)))
    only = _rec("1", 100)
    assert envelope.relieve([only]) == "" and not only.paused


def test_pressure_pauses_the_newest_and_room_resumes_only_what_it_paused(monkeypatch):
    monkeypatch.setattr(envelope, "policy", lambda: {"worker_nice": 10, "admit_free_ratio": 0.2,
                                                     "pause_free_ratio": 0.1, "admit_wait_s": 60})
    old, new, his = _rec("1", 100), _rec("2", 200), _rec("3", 50, paused=True)   # «his» = paused by the operator
    monkeypatch.setattr(envelope, "measured", lambda: (2 * GB, int(0.05 * 2 * GB)))
    assert envelope.relieve([old, new, his]) == "paused 2" and new.paused and not old.paused
    monkeypatch.setattr(envelope, "measured", lambda: (2 * GB, int(0.6 * 2 * GB)))
    assert envelope.relieve([old, new, his]) == "resumed 2" and not new.paused
    assert his.paused, "a worker the operator paused was resumed by the envelope"


def test_a_worker_runs_below_the_voices_priority(monkeypatch):
    got = []
    monkeypatch.setattr(os, "nice", lambda n: got.append(n))
    monkeypatch.setattr(envelope, "policy", lambda: {"worker_nice": 10, "admit_free_ratio": 0.2,
                                                     "pause_free_ratio": 0.1})
    seen = []
    envelope.preexec(also=lambda: seen.append("sandbox"))()
    assert got == [10] and seen == ["sandbox"]


def test_the_envelope_is_declared_data_in_ratios():
    pol = envelope.policy()
    assert 0 < pol["pause_free_ratio"] < pol["admit_free_ratio"] < 1 and pol["worker_nice"] > 0
