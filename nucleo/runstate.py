"""nucleo/runstate.py — IS THE AGENT RUNNING OR STOPPED? The single source of truth, server-side (V2-092).

## The bug it fixes

The ⏻ button had existed since V2-039 and since V2-065 already froze the Brain Workers (SIGSTOP), but its state lived
ONLY in the browser’s `localStorage` (`hb_power_off`). Real consequences, reported by the operator with the
agent STOPPED in front of them:

  - A YouTube video kept playing, and when the page was RELOADED it started again on its own (its persisted state
    said “playing” and its `<iframe>` is created with `autoplay=1`).
  - Music played AT THE SAME TIME as the video — two widgets fighting over the speaker.
  - Background `tick()` calls kept running: a “stopped” agent that continued polling connectors.

In other words: ⏻ stopped the VOICE and the WORKERS, and nothing else. The rest did not even know, because there
was nobody to ask: the server did not know that the operator had stopped the agent. State that governs the whole
system cannot live in `localStorage` — it is per-browser, per-origin, and the backend (widgets, background, crons,
the cloud) cannot see it.

## The model

**A single switch, on the server, persisted** (`sys_kv`, survives an engine restart because it is the operator’s
INTENTION, not a process state). Everything that can be “running” consults it or receives it:

    STOP  →  workers FROZEN (SIGSTOP, reversible) · producer widgets SUSPENDED · background without ticks
             · crons do not fire · nothing new starts · OBSERVABILITY SESSION CLOSED (2026-08-16)
    START → workers CONTINUE where they were · background returns · crons return
             · **widgets are NOT resumed** (explicit operator decision, see below)

**Deliberate asymmetry.** Stopping is total; starting does NOT revive playback. Operator’s words
(2026-08-13): “if I say to start the system, that does not necessarily mean the widgets should be started again;
the user should decide manually whether they want to resume listening to music or a podcast or playing a
video.” What MUST continue is the WORK: a Brain Worker halfway through creating a widget or performing a
complex search is frozen and continues exactly where it was. The difference is who owns the intent: the operator
started the music for themselves; they commissioned the task and are waiting for its result.

## Boundary

This module does NOT know how to pause anything: it knows WHO must be notified and in what order. The how lives in
its owner (`dispatch.pause_all` for workers, `widgets/producers.py` for the canvas, `widgets/background.py` for the
cycles). This lets a new component that can be “running” hook in here with one line without reimplementing the
policy.
"""
from __future__ import annotations

import os
import time

from loguru import logger

RUNNING = "running"
STOPPED = "stopped"

_KV_KEY = "run:state"

# In-process cache: `stopped()` is queried by HOT paths (every widget action, every background tick),
# and cannot incur a SQLite read every time. `sys_kv` is the durable backup, not the source for every
# read: this process is the only one that writes the switch.
_state: dict = {"value": None, "at": 0.0, "src": ""}

# ── DEFERRED stop (V2-092 addenda, 2026-08-15) ─────────────────────────────────────────────────────────────
# A voice turn with a model call REALLY in flight (`FastClient.stream()`, the network call, not the rest of the
# turn) can't be cut mid-response. But the operator was explicit: the stop's completion isn't a TIMER's job —
# it's triggered by a CONCRETE ACTION (that turn genuinely ending), and a clock only applies to the case where
# no close signal ever arrives (see `observability/identity.py`). That's why this counter is purely in-memory
# (not `sys_kv`): a process restart already kills any turn in flight, so losing the deferred-stop intent in
# that case is correct, not a bug.
_inflight: dict = {"n": 0}
_pending: dict = {"stop": False, "src": ""}


def inflight_count() -> int:
    return _inflight["n"]


def pending_stop() -> bool:
    return _pending["stop"]


def enter_inflight() -> None:
    """A turn just started a real network call to the model. Call ONCE per outgoing call."""
    _inflight["n"] += 1


async def exit_inflight() -> None:
    """That network call just ended (success, provider error, or cancellation — doesn't matter which). If it
    was the LAST one in flight and a stop was pending, this is what completes it — never a clock."""
    _inflight["n"] = max(0, _inflight["n"] - 1)
    if _inflight["n"] == 0 and _pending["stop"]:
        src = _pending["src"]
        _pending["stop"] = False
        _pending["src"] = ""
        await _do_stop(src)


def _load() -> str:
    if _state["value"] is not None:
        return _state["value"]
    val = RUNNING
    try:
        from memory import api as memory
        d = memory.kv_get(_KV_KEY)          # kv_get/kv_set already handle JSON: the dict is stored as-is
        if isinstance(d, dict) and d.get("value") in (RUNNING, STOPPED):
            val = d["value"]
            _state["at"] = float(d.get("at") or 0.0)
            _state["src"] = str(d.get("src") or "")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate: no pude leer el estado persistido ({e!r}) — asumo «en marcha»")
    _state["value"] = val
    return val


def _persist(value: str, src: str) -> None:
    _state.update({"value": value, "at": time.time(), "src": src})
    try:
        from memory import api as memory
        memory.kv_set(_KV_KEY, {"value": value, "at": _state["at"], "src": src})
    except Exception as e:  # noqa: BLE001
        # A persistence failure cannot prevent stopping: the in-memory switch is already set and the whole
        # system obeys it NOW. The only thing lost is surviving an engine restart.
        logger.warning(f"runstate: el estado no se pudo persistir ({e!r}) — vale para esta ejecución")


def state() -> str:
    """`"running"` | `"stopped"`. Never raises: when in doubt, “running” (a read failure must not leave the
    operator with an agent that refuses to work)."""
    try:
        return _load()
    except Exception:
        return RUNNING


def stopped() -> bool:
    return state() == STOPPED


def running() -> bool:
    return not stopped()


def snapshot() -> dict:
    """What the frontend sees (`GET /api/run`): the state, when it changed, and who changed it.

    `state` can be `"pausing"` — genuinely RUNNING underneath (nothing has been frozen yet: see `_pending`), but
    with a stop requested that's waiting for the last turn in flight to end. `running` stays `True` through
    that stretch on purpose: underneath, nothing has actually stopped yet."""
    val = state()
    effective = "pausing" if (val == RUNNING and _pending["stop"]) else val
    return {"state": effective, "running": val == RUNNING, "at": _state["at"], "src": _state["src"]}


def _emit(label: str, text: str, extra: dict) -> None:
    try:
        from voice.observer import emit
        emit("run", label, text=text, extra=extra)
    except Exception:
        pass


async def stop(src: str = "operator") -> dict:
    """Requests the stop. With any turn REALLY in flight (`_inflight`, see above), it doesn't stop on the spot:
    it's DEFERRED (`_pending["stop"] = True`, state `"pausing"` — nothing frozen yet) until `exit_inflight()`
    completes it on its own. Pressing ⏻ again while in `"pausing"` CANCELS it (since nothing was touched yet,
    there's nothing to undo). With no turns in flight, this is the usual stop — see `_do_stop`."""
    if _inflight["n"] > 0:
        if _pending["stop"]:
            _pending["stop"] = False
            _pending["src"] = ""
            _emit("resumed", f"stop cancelled by {src} — still running", {"src": src})
            return {"ok": True, "state": RUNNING, "cancelled": True}
        _pending["stop"] = True
        _pending["src"] = src
        _emit("pausing", f"turn in flight — the stop requested by {src} is waiting for it to finish",
              {"src": src, "inflight": _inflight["n"]})
        return {"ok": True, "state": "pausing"}
    return await _do_stop(src)


async def _do_stop(src: str = "operator") -> dict:
    """STOP THE AGENT for real. Freezes everything that may be working or producing, in an order that
    matters:

    1. **The switch first.** While everything else is stopping, new actions may arrive; with the flag already
       set, the action funnel (`widgets/server_api.py`) rejects them instead of starting something right behind
       the stop.
    2. **The observability session is closed** (2026-08-16, real finding: with the agent stopped and the browser
       open, background noise —~1Hz pulse, state projection— kept reaching the session that was already open and
       kept it “IN PROGRESS” forever in the master, with its flows growing). `end_session` emits its own closing
       `system` event —`stamp_identity` only READS the session for that category; it never reopens it—so anything
       arriving AFTER the stop remains sessionless, as a deliberate stop should be.
    3. **Workers** (SIGSTOP, reversible) — frozen at the exact spot, not dead.
    4. **Producer widgets** — each through its declared suspension action (see `widgets/producers.py`).

    Idempotent: stopping twice breaks nothing (an already closed session has nothing to close). Never raises —
    each step is isolated, because a half-completed stop is worse than none: the operator believes they stopped it and something
    keeps playing."""
    _persist(STOPPED, src)
    try:
        from observability import identity
        identity.end_session(src)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate.stop: the observability session could not be closed: {e!r}")
    frozen, suspended = 0, []
    try:
        from nucleo import dispatch
        frozen = dispatch.pause_all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate.stop: los workers no se pudieron congelar: {e!r}")
    try:
        from widgets import producers
        suspended = await producers.suspend_all(reason="agent_stopped")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate.stop: los widgets no se pudieron suspender: {e!r}")
    logger.info(f"runstate: PARADO por {src} — {frozen} worker(s) congelado(s), "
                f"{len(suspended)} widget(s) suspendido(s): {suspended or '—'}")
    _emit("stop", f"parado por {src}: {frozen} worker(s), {len(suspended)} widget(s)",
          {"src": src, "workers": frozen, "widgets": suspended})
    return {"ok": True, "state": STOPPED, "workers": frozen, "widgets": suspended}


async def start(src: str = "operator") -> dict:
    """START THE AGENT. Continues frozen WORK (SIGCONT) and allows background/crons/actions again.

    **Does NOT resume widgets on purpose** — see the asymmetry documented above. Starting the music again is an
    operator action, not a consequence of powering on.

    This is also how a DEFERRED stop gets CANCELLED (`_pending`, see `stop()`): the frontend, on a second ⏻
    click while it's blinking "pausing", calls this same endpoint (it's the "turn on" button from its point of
    view, not a new one). Since nothing had actually been frozen yet, cancelling is free — the rest of this
    (idempotent) body just confirms it's still running."""
    if _pending["stop"]:
        _pending["stop"] = False
        _pending["src"] = ""
        _emit("resumed", f"stop cancelled by {src} — still running", {"src": src})
    _persist(RUNNING, src)
    resumed = 0
    try:
        from nucleo import dispatch
        resumed = dispatch.resume_all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate.start: los workers no se pudieron reanudar: {e!r}")
    # V2-516: STARTING the agent also revives a dead HEARTBEAT (nucleo/loop.py). The lifespan starts it
    # exactly once and never retries, so any import-time failure leaves the engine up with no pulse — crons
    # silent, ECG flat — and before this, the operator's ⏻, the one gesture that should fix a stopped state
    # (feedback: visible state over silent state), did nothing. Measured 2026-08-31: a syntax-broken instant
    # of loop.py (a translation pass writing the file as the engine imported it) produced exactly that.
    heartbeat = False
    try:
        from config.v2 import active_brain
        if active_brain() == "nucleo" and os.getenv("ZAELAR_LOOP", "1") == "1":
            from nucleo import loop as _loop
            if not _loop.is_running():
                _loop.start()
                logger.info(f"runstate.start: heartbeat was DOWN — revived by {src}")
            heartbeat = _loop.is_running()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runstate.start: heartbeat revive failed: {e!r}")
    logger.info(f"runstate: EN MARCHA por {src} — {resumed} worker(s) continúan donde estaban "
                f"(los widgets NO se reanudan: los reanuda el operador)")
    _emit("start", f"en marcha por {src}: {resumed} worker(s) continúan", {"src": src, "workers": resumed})
    return {"ok": True, "state": RUNNING, "workers": resumed, "heartbeat": heartbeat}


def _reset_for_tests() -> None:
    """Tests only: forgets the in-process cache so the next `state()` re-reads `sys_kv`, and clears any turn in
    flight / deferred stop a previous test left half-done."""
    _state.update({"value": None, "at": 0.0, "src": ""})
    _inflight.update({"n": 0})
    _pending.update({"stop": False, "src": ""})
