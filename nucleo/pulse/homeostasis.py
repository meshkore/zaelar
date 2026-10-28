#
# homeostasis.py — the system's AUTONOMOUS HEARTBEAT (V2-070). It keeps the MACHINE healthy and never thinks: no
# model, a sibling of the brain (FlashBrain drives, Susurro audits the conversation, this keeps the body alive),
# with the same start()/stop() pattern as the other lifespan supervisors. Each resource is binary, healthy or
# degraded → heal:
#   1) LiveKit ENGINE — degradation is read from the SDK log (in-process); recycle the embedded worker when SAFE
#      (voice off + channel idle), otherwise tell the operator.
#   2) LOGS — rotate by rename (writers append with "a", so the next write recreates the file) and prune old ones.
#   3) CAPSULES — evict concluded, old per-peer state (sys_kv `capsule:*`) and bound the total.
# Never touches the FlashBrain or the operator's memory; fail-open; every action emits `homeostasis`;
# kill-switch `ZAELAR_HOMEOSTASIS=0`.
#
from __future__ import annotations

import asyncio
import logging
import os
import time

log = logging.getLogger(__name__)

# ── config (infra, not UI — env-overridable for power users/tests) ──────────────────────────────────────────────
_PERIOD_S = float(os.getenv("HOMEOSTASIS_PERIOD_S", "60"))       # heartbeat period
# The thresholds the pure decisions default to live with them (no import cycle in either order):
from nucleo.pulse.homeostasis_policy import (  # noqa: E402
    _CAP_MAX, _CAP_TTL_S, _IDLE_S, _LK_THRESHOLD, _LK_WINDOW_S, _LOG_CAP_BYTES)

_RECYCLE_COOLDOWN_S = float(os.getenv("HOMEOSTASIS_RECYCLE_COOLDOWN_S", "600"))  # at most one recycle per 10 min

_LOG_KEEP = int(os.getenv("HOMEOSTASIS_LOG_KEEP", "3"))             # rotated files to keep


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOG_DIR = os.getenv("ZAELAR_LOG_DIR") or os.path.join(_REPO_ROOT, ".meshkore", "logs")
_ROTATABLE = ("timeline-latest.jsonl", "meshkore.jsonl")

# LiveKit degradation marks (timestamps), filled by the in-process logging watcher
_marks: list[float] = []
_last_recycle: float = 0.0
_alerted: set[str] = set()      # operator alerts already given (once per incident)
_recycle_requested: str = ""    # explicit recycle request (reason) — see request_recycle()


def request_recycle(reason: str) -> None:
    """Ask for the embedded LiveKit worker to be recycled on the next beat (V2-655). For a session that CLOSED
    while room and server stayed up — no log marker fires, so the piece that knows it died asks by name. Only the
    cooldown gates it; `safe_to_recycle` is skipped on purpose: a dead session has no conversation to cut."""
    global _recycle_requested
    _recycle_requested = (reason or "").strip() or "unspecified"
    log.warning("homeostasis: recycle requested — %s", _recycle_requested)


def enabled() -> bool:
    return os.getenv("ZAELAR_HOMEOSTASIS", "1").lower() not in ("0", "false", "off", "no")


# ── LiveKit engine DETECTION — in-process signal from the SDK logging ────────────────────────────────────────────
_MARKERS = (
    "wait_pc_connection timed out",
    "entrypoint did not exit",
    # The job executor missed its health ping (a voice worker once went dead for hours after it). A blocked
    # thread can fire it transiently, so it counts in the same window+threshold and the same safety gate.
    "job executor is unresponsive",
)


class _LKWatcher(logging.Handler):
    """Listens to the `livekit` logger (and children): stamps a mark on each degraded-engine message. Emits nothing."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage().lower()
        except Exception:
            return
        if any(m in msg for m in _MARKERS):
            _marks.append(time.time())
            if len(_marks) > 256:          # bound memory (a probe, not a history)
                del _marks[:128]


_watcher = _LKWatcher()
_watcher.setLevel(logging.WARNING)


# ── heals (IO; each fail-open) ─────────────────────────────────────────────────────────────────────────────────
def _emit(label: str, text: str = "", extra: dict | None = None) -> None:
    try:
        from voice import observer
        observer.emit("homeostasis", label, text, extra=extra or {})
    except Exception:
        pass


async def _alert(key: str, title: str, text: str) -> None:
    """Tell the operator ONCE per incident (dedup by `key`), ON SCREEN ONLY. V2-768 — never spoken: a spoken
    alert opened the reply window and his next sentence to someone else ran as an order. Nor a note for the brain
    (`proactive.notify(speak=False)`); only the UI half of `notify` is kept."""
    if key in _alerted:
        return
    _alerted.add(key)
    _emit("alert", f"{title}: {text}")
    try:
        from voice.observer import emit
        emit("homeostasis", ("🔔 " + title)[:60], text=text, role="assistant", extra={"title": title})
    except Exception:
        pass


def _recent_activity_ts() -> float:
    """Last channel activity: the timeline's mtime (voice/chat/cluster write there). 0 if none."""
    try:
        return os.path.getmtime(os.path.join(_LOG_DIR, "timeline-latest.jsonl"))
    except OSError:
        return 0.0


def _voice_on() -> bool:
    try:
        from server import state as S
        return bool(S.STATE.get("voice"))
    except Exception:
        return False


async def _consume_recycle_request(app, now: float) -> bool:
    """Honour a pending request_recycle() — the flag SURVIVES the cooldown window so a request during it is
    honoured on a later beat, never dropped. True if a recycle actually ran."""
    global _recycle_requested
    if not _recycle_requested or now - _last_recycle < _RECYCLE_COOLDOWN_S:
        return False
    reason, _recycle_requested = _recycle_requested, ""
    _emit("degraded", f"reciclado solicitado: {reason}")
    if await _recycle_livekit(app):
        try:
            from voice import health_state
            health_state.clear("voice")
        except Exception:
            pass
        return True
    return False


async def _recycle_livekit(app) -> bool:
    """Recreate the EMBEDDED LiveKit worker (aclose + make_server + new task) without restarting the process."""
    global _last_recycle
    try:
        old = getattr(app.state, "lk_server", None)
        if old is not None:
            try:
                await old.aclose()
            except Exception as e:  # noqa: BLE001
                log.warning("homeostasis: aclose del motor viejo falló: %s", e)
        from voice.engine.pipeline.agent import make_server
        new = make_server()
        app.state.lk_server = new
        devmode = os.getenv("ZAELAR_ENV", "dev").lower() != "prod"
        app.state.lk_task = asyncio.create_task(new.run(devmode=devmode))
        _last_recycle = time.time()
        _marks.clear()                       # the degradation window starts over
        _emit("recycle", "motor LiveKit reciclado (worker embebido re-registrado)")
        log.info("homeostasis: motor LiveKit reciclado")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: reciclado del motor falló: %s", e)
        return False


def _rotate_log(path: str, *, keep: int = _LOG_KEEP) -> None:
    """Rotate by rename (the next append recreates the file) and keep the newest `keep` rotated copies."""
    try:
        if not os.path.exists(path):
            return
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        os.rename(path, f"{path}.{stamp}")
        _emit("rotate", f"{os.path.basename(path)} rotado ({stamp})")
        base = os.path.basename(path)
        d = os.path.dirname(path)
        rotated = sorted(
            (os.path.join(d, f) for f in os.listdir(d) if f.startswith(base + ".")),
            key=os.path.getmtime, reverse=True,
        )
        for old in rotated[keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: rotación de %s falló: %s", path, e)


# ── the HEARTBEAT ───────────────────────────────────────────────────────────────────────────────────────────────
async def _tick(app) -> None:
    """One beat: the three checks, each isolated."""
    now = time.time()

    # 1) LiveKit ENGINE
    try:
        if getattr(app, "state", None) is not None and getattr(app.state, "lk_server", None) is not None:
            # 1a) EXPLICIT request (a dead voice session, see request_recycle)
            await _consume_recycle_request(app, now)
            if livekit_degraded(_marks, now):
                if now - _last_recycle < _RECYCLE_COOLDOWN_S:
                    pass  # recycled recently: no recycle loop
                elif safe_to_recycle(_voice_on(), _recent_activity_ts(), now):
                    _emit("degraded", "motor LiveKit degradado (bucle WebRTC) — reciclando en frío")
                    ok = await _recycle_livekit(app)
                    if ok:
                        _alerted.discard("lk_degraded")  # re-arm the alert for a later incident
                else:
                    await _alert("lk_degraded", "Motor de voz degradado",
                                 "El motor LiveKit se está atascando pero hay actividad en curso; no lo reinicio "
                                 "para no cortarte. Si notas cortes, dime y lo reinicio.")
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: chequeo del motor falló: %s", e)

    # 2) LOGS
    try:
        sizes = []
        for name in _ROTATABLE:
            p = os.path.join(_LOG_DIR, name)
            try:
                sizes.append((p, os.path.getsize(p)))
            except OSError:
                pass
        for p in logs_to_rotate(sizes):
            _rotate_log(p)
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: chequeo de logs falló: %s", e)

    # 3) CAPSULES
    try:
        from memory import api as memory
        keys = memory.kv_keys("capsule:")
        items = [(k, memory.kv_get(k) or {}) for k in keys]
        for key in capsules_to_evict(items, now):
            memory.kv_del(key)
        evicted = len(capsules_to_evict(items, now))
        if evicted:
            _emit("evict", f"{evicted} cápsula(s) muerta(s) evictada(s)")
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: chequeo de cápsulas falló: %s", e)


async def _loop(app) -> None:
    # first beat after boot settles, then periodic
    try:
        await asyncio.sleep(min(_PERIOD_S, 30))
    except asyncio.CancelledError:
        return
    while True:
        try:
            await _tick(app)
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001
            log.warning("homeostasis: latido falló (continúo): %s", e)
        try:
            await asyncio.sleep(_PERIOD_S)
        except asyncio.CancelledError:
            return


_task: asyncio.Task | None = None


def start(app=None) -> None:
    """Start the heartbeat (idempotent); called from the server lifespan."""
    global _task
    if not enabled():
        log.info("homeostasis: apagado por ZAELAR_HOMEOSTASIS")
        return
    if _task and not _task.done():
        return
    logging.getLogger("livekit").addHandler(_watcher)   # in-process engine probe
    _task = asyncio.create_task(_loop(app))
    _emit("start", "latido autónomo en marcha")
    log.info("homeostasis: latido autónomo iniciado")


async def stop() -> None:
    global _task
    try:
        logging.getLogger("livekit").removeHandler(_watcher)
    except Exception:
        pass
    if _task:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None


from nucleo.pulse.homeostasis_policy import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    capsules_to_evict, livekit_degraded, logs_to_rotate, safe_to_recycle)
