"""nucleo/workers/envelope.py — background work can never starve the voice (V2-831 T-27).

Measured on the operator's cloud host (1 vCPU / 2 GB, no swap): free memory fell 1275 MB -> 0 over one voice session
while two errands ran and was not given back when they ended; the VAD fell behind real time («slower than realtime»,
«job executor unresponsive») and the host froze. The voice and the workers share the host with no boundary.

The boundary, as mechanism and data (`config/resources.default.json`, every number a RATIO of what the host measures):
  · a worker process tree runs at a LOWER scheduling priority (`preexec`);
  · a new worker is ADMITTED only while measured free memory is above the floor (`admits`, `wait_for_room`);
  · above the ceiling of pressure the NEWEST running worker is paused, and resumed when there is room again
    (`relieve`), the same reversible pause the ⏻ uses;
  · its process GROUP is reaped when the errand ends (the providers' `stop`), so nothing it spawned outlives it.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from loguru import logger

_HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
_DEFAULTS = {"worker_nice": 10, "admit_free_ratio": 0.2, "pause_free_ratio": 0.1, "admit_wait_s": 60,
             "voice_lag_s": 0.5}
_shed = {"until": 0.0}      # T-30: the voice asked for room — no new worker until then, the last one started paused


def shed(seconds: float) -> None:
    """The voice is falling behind (T-30): hold new workers for `seconds` and relieve as under memory pressure."""
    _shed["until"] = time.monotonic() + float(seconds)


def shedding() -> bool:
    return time.monotonic() < _shed["until"]


def policy() -> dict:
    """The declared envelope: the repo default, then the deployment's own file over it."""
    out = dict(_DEFAULTS)
    for path in (os.path.join(_HERE, n) for n in ("resources.default.json", "resources.json")):
        if not os.path.exists(path):     # the deployment's own file is optional
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                # every declared key, not only the envelope's own: the watchdog (T-28) and the summary (T-31) read here
                out.update({k: v for k, v in json.load(fh).items() if not k.startswith("_")})
        except Exception as e:  # noqa: BLE001 — a broken file says so and the defaults hold
            logger.warning(f"envelope: {path} unreadable ({e!r}) — the defaults hold")
    return out


def measured() -> tuple[int, int]:
    """`(total, available)` bytes of the host's memory, as it is NOW."""
    import psutil
    vm = psutil.virtual_memory()
    return int(vm.total), int(vm.available)


def admits(total: int, available: int, pol: dict | None = None) -> bool:
    return available >= float((pol or policy())["admit_free_ratio"]) * total


def under_pressure(total: int, available: int, pol: dict | None = None) -> bool:
    return available < float((pol or policy())["pause_free_ratio"]) * total


def preexec(also=None):
    """The worker's `preexec_fn`: lower scheduling priority than the voice, after `also` (a sandbox's own limits).
    Fail-soft (the child still runs)."""
    nice = int(policy()["worker_nice"])

    def _apply():
        if also is not None:
            also()
        if hasattr(os, "nice"):          # lowering one's own priority never needs a privilege on a Unix host
            os.nice(nice)
    return _apply


async def wait_for_room(say=None, late=None, *, poll_s: float = 5.0) -> bool:
    """Hold a new worker until the host has room for it, against a CLOCK (`admit_wait_s`, data). True when admitted;
    False when the deadline passed: the worker then starts ANYWAY — at its lower priority, with `late()` said and a
    loud event — because «no worker ever starts» on a busy host is worse than one more worker under watch."""
    deadline = time.monotonic() + float(policy()["admit_wait_s"])
    said = False
    while shedding() or not admits(*measured()):
        if not said and say is not None:
            said = bool(say() or True)
        if time.monotonic() >= deadline:
            logger.warning("envelope: no room for a new worker by the deadline — it starts anyway, under watch")
            try:
                from voice.observer import emit
                emit("alert", "Poca memoria libre: el encargo arranca igual, con menos prioridad.", role="system",
                     extra={"cat": "worker", "kind_diag": "envelope_late"})
            except Exception as e:  # noqa: BLE001 — the start must not wait on its own notice
                logger.debug(f"envelope: late notice not emitted: {e!r}")
            if late is not None:
                late()
            return False
        await asyncio.sleep(poll_s)
    return True


def relieve(records) -> str:
    """Under pressure pause the NEWEST running worker — only while ANOTHER keeps running, so the one errand he is waiting
    on is never the one frozen; with room again resume what it paused. Returns what it did."""
    total, avail = measured()
    live = sorted((r for r in records if getattr(r, "status", "") == "running" and getattr(r, "session", None)),
                  key=lambda r: float(getattr(r, "started", 0) or 0))
    if shedding() or under_pressure(total, avail):
        running = [r for r in live if not getattr(r, "paused", False)]
        newest = running[-1] if len(running) >= 2 else None
        if newest is not None and newest.session.pause():
            newest.paused_by = "envelope"          # only ITS pauses are undone here, never the operator's ⏻
            return f"paused {newest.task_id}"
    elif admits(total, avail) and not shedding():
        for r in live:
            if getattr(r, "paused_by", "") == "envelope" and r.session.resume():
                r.paused_by = ""
                return f"resumed {r.task_id}"
    return ""
