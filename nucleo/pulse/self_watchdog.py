"""nucleo/pulse/self_watchdog.py — a frozen engine recovers itself (V2-831 T-28, engine half).

Liveness had no actuator: on a small host that ran out of memory the event loop stopped answering, the voice went
deaf and nothing in the process acted — the pulse, homeostasis and the worker envelope all run ON that loop. This
watchdog is a THREAD, so it still runs when the loop does not:

  * every `_PERIOD_S` it posts a beat onto the server loop and reads how long ago the last one landed (the loop's
    own answer, not a guess), and the host's free memory through the worker envelope (`envelope.measured`);
  * unhealthy — the loop has not answered for `freeze_s`, or free memory is under the envelope's pause floor — it
    SHEDS first: an event, admission held (`envelope.shed`) and the most recently started worker paused, the same
    rule the envelope applies (never the only one);
  * still unhealthy after `stuck_s` (the bound is a clock, never a count), and only when the process runs under a
    supervisor (`ZAELAR_SUPERVISED=1`, a seam a deployment sets), it EXITS: the server's own graceful shutdown with a
    non-zero status (`EXIT_CODE`) so an on-failure restart policy starts it again; a loop too frozen to shut down is
    ended after `exit_grace_s`. Without a supervisor nothing would start it again, so it sheds and says so — never exits.

Every number is declared beside the envelope's (`config/resources.default.json`). Healthy again before `stuck_s`,
the episode closes with an event.
"""
from __future__ import annotations

import os
import threading
import time

from loguru import logger

_PERIOD_S = 2.0
EXIT_CODE = 75                                  # EX_TEMPFAIL: «try again» to a supervisor, never «stopped on purpose»
_DEFAULTS = {"freeze_s": 15.0, "stuck_s": 120.0, "exit_grace_s": 15.0}
_state: dict = {"beat": 0.0, "since": 0.0, "shed": False, "exiting": False, "code": 0, "thread": None, "stop": None}
_exit_hook: dict = {"fn": None}


def request_exit(fn) -> None:
    """Registered by the entrypoint: the callable that asks the server to shut down gracefully."""
    _exit_hook["fn"] = fn


def exit_code() -> int:
    """The status the process ends with: `EXIT_CODE` once the watchdog asked for the exit, else 0."""
    return int(_state["code"] or 0)


def supervised() -> bool:
    return os.getenv("ZAELAR_SUPERVISED", "") == "1"


def policy() -> dict:
    from nucleo.workers import envelope
    pol = envelope.policy()
    return {k: float(pol.get(k, v)) for k, v in _DEFAULTS.items()}


def decide(now: float, beat_age: float, pressure: bool, since: float, pol: dict, can_exit: bool) -> str:
    """One reading → `ok` · `recovered` · `shed` (unhealthy, first or still within `stuck_s`) · `exit`. Pure."""
    unhealthy = beat_age > pol["freeze_s"] or pressure
    if not unhealthy:
        return "recovered" if since else "ok"
    if since and now - since >= pol["stuck_s"] and can_exit:
        return "exit"
    return "shed"


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("alert", label, role="system", extra={"cat": "health", "kind_diag": "self_watchdog", **extra})
    except Exception as e:  # noqa: BLE001 — the watchdog never dies of its own report
        logger.warning(f"self_watchdog: {label} ({extra}) — not emitted: {e!r}")


def _shed(pol: dict) -> None:
    from nucleo import dispatch
    from nucleo.workers import envelope
    envelope.shed(pol["stuck_s"])
    did = envelope.relieve(list(dispatch._SESSIONS.values()))
    logger.warning(f"self_watchdog: shedding load ({did or 'nothing to pause'})")


def _exit(pol: dict) -> None:
    """The server's graceful shutdown with a non-zero status; a loop too frozen to run it is ended after the grace."""
    _state["exiting"], _state["code"] = True, EXIT_CODE
    try:
        if _exit_hook["fn"] is not None:
            _exit_hook["fn"]()
    except Exception as e:  # noqa: BLE001 — the hard exit below still runs
        logger.warning(f"self_watchdog: graceful exit request failed: {e!r}")
    t = threading.Timer(pol["exit_grace_s"], lambda: os._exit(EXIT_CODE))
    t.daemon = True
    t.start()


def tick(loop, now: float | None = None) -> str:
    """One reading of the loop and the memory, and its consequence. Returns the decision."""
    from nucleo.workers import envelope
    now = time.monotonic() if now is None else now
    try:
        loop.call_soon_threadsafe(_state.__setitem__, "beat", time.monotonic())
    except RuntimeError as e:                     # the loop is closed: the process is ending anyway
        logger.debug(f"self_watchdog: loop closed: {e!r}")
        return "ok"
    pol = policy()
    total, avail = envelope.measured()
    pressure = envelope.under_pressure(total, avail)
    age = now - (_state["beat"] or now)
    what = decide(now, age, pressure, _state["since"], pol, supervised() and not _state["exiting"])
    facts = {"loop_age_s": round(age, 1), "free_ratio": round(avail / total, 3) if total else None}
    if what == "recovered":
        _state["since"], _state["shed"] = 0.0, False
        _emit("El motor se ha recuperado — vuelve a responder.", **facts)
    elif what == "shed":
        _state["since"] = _state["since"] or now
        if not _state["shed"]:
            _state["shed"] = True
            _emit("El motor no responde o va sin memoria — libero carga.", **facts, supervised=supervised())
        _shed(pol)
    elif what == "exit":
        _emit("El motor sigue bloqueado — salgo limpio para que lo reinicien.", **facts, code=EXIT_CODE)
        _exit(pol)
    return what


def start(loop=None) -> bool:
    """Start the thread watching `loop` (the running one by default). Idempotent; never raises."""
    if _state["thread"] is not None:
        return False
    try:
        import asyncio
        loop = loop or asyncio.get_running_loop()
    except RuntimeError as e:
        logger.debug(f"self_watchdog: no running loop to watch: {e!r}")
        return False
    stop = threading.Event()
    _state.update(beat=time.monotonic(), since=0.0, shed=False, stop=stop)

    def run():
        while not stop.wait(_PERIOD_S):
            try:
                tick(loop)
            except Exception as e:  # noqa: BLE001 — one bad reading never ends the watch
                logger.warning(f"self_watchdog: tick failed: {e!r}")
    _state["thread"] = threading.Thread(target=run, name="self-watchdog", daemon=True)
    _state["thread"].start()
    return True


def stop() -> None:
    if _state["stop"] is not None:
        _state["stop"].set()
    _state.update(thread=None, stop=None)
