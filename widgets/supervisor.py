#
# supervisor.py — HOST for "backed" widgets (kind:"backed"), designed in zaelar-modules.md §Widget-apps and built
# with the browser (INI-016, first backed widget). A "passive" widget (the usual kind) has no process: view_data reads
# on demand and its only writer is its own ctx.action or Hermes. A "backed" widget is a small APP with a live backend
# (the browser has a headless Chromium inside): its folder provides an `owner.py` with
# `async start()/stop()/handle(action,payload)`, and THIS supervisor —started in server lifespan, in the SAME loop as
# voice— discovers it in the catalog, imports it, and governs it:
#
#   • SINGLE WRITER by construction: the owner is the only writer to widgets/_data/<id>/ (via store.save → SSE refresh
#     of the open card). The face (data.py + widget.js) becomes READ-ONLY + ENQUEUE: an operator action (ctx.action) or
#     Hermes ([[widget.data]]) does NOT touch the store; it leaves the command in the MAILBOX (an asyncio.Queue) that
#     the owner drains in order. Removes the two-writer race by design, not with locks.
#   • SUPERVISION: if the owner blows up, retry with exponential backoff; after MAX_FAILS consecutive failures,
#     DISABLE it (degrade to last known frozen state instead of hammering) — a down owner can never bring down voice or
#     another widget. Everything is traced through voice/observer (kind "backed") for testers.
#
import asyncio
import importlib
import os

from loguru import logger

from . import runtime

_MAX_FAILS = int(os.environ.get("WIDGETS_BACKED_MAX_FAILS", "4"))   # consecutive start() failures before disabling
_QUEUE_MAX = int(os.environ.get("WIDGETS_BACKED_QUEUE", "128"))


def _emit(label: str, wid: str, text: str = "") -> None:
    """Backed lifecycle observability → /events + /api/debug (kind 'backed'). Never raises."""
    try:
        from voice.observer import emit
        emit("backed", label, text=(f"{wid}: {text}" if text else wid), extra={"id": wid})
    except Exception:
        pass


class _Service:
    """A live backed widget: its owner + mailbox + supervised task. The mailbox (Queue) SURVIVES owner restarts (lives
    in _Service, not inside _run) — a crash does not lose already queued commands."""

    def __init__(self, wid: str, owner):
        self.wid = wid
        self.owner = owner
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self.task: asyncio.Task | None = None
        self.fails = 0
        self.disabled = False

    async def _run(self) -> None:
        backoff = 1.0
        while not self.disabled:
            try:
                await self.owner.start()
                _emit("start", self.wid)
                self.fails = 0
                backoff = 1.0
                while True:                                   # mailbox: drain commands in order, one by one
                    action, payload = await self.queue.get()
                    try:
                        await self.owner.handle(action, payload)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:                    # a failure in ONE command (bad URL, timeout) does NOT restart
                        _emit("cmd_error", self.wid, f"{action}: {e}")
                        logger.warning(f"backed[{self.wid}] handle {action!r} falló: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:                            # owner crash (start or something fatal) → retry
                self.fails += 1
                _emit("crash", self.wid, f"{e} (fallo {self.fails}/{_MAX_FAILS})")
                logger.warning(f"backed[{self.wid}] cayó: {e} (fallo {self.fails}/{_MAX_FAILS})")
                try:
                    await self.owner.stop()
                except Exception:
                    pass
                if self.fails >= _MAX_FAILS:
                    self.disabled = True
                    _emit("disabled", self.wid, "demasiados fallos; congelado en último estado")
                    logger.error(f"backed[{self.wid}] DESACTIVADO tras {self.fails} fallos")
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def enqueue(self, action: str, payload: dict) -> bool:
        if self.disabled:
            _emit("dropped", self.wid, f"{action} (widget desactivado)")
            return False
        try:
            self.queue.put_nowait((action, payload or {}))
            return True
        except asyncio.QueueFull:
            _emit("dropped", self.wid, f"{action} (buzón lleno)")
            logger.warning(f"backed[{self.wid}] buzón lleno; se descarta {action!r}")
            return False


_services: dict[str, _Service] = {}


def _load_owner(wid: str):
    """Import widgets/<id>/owner.py. Lazy import: an owner that does not import (e.g. missing dependency) disables ONLY
    that widget, never server startup."""
    try:
        return importlib.import_module(f"widgets.{wid}.owner")
    except Exception as e:
        _emit("import_error", wid, str(e))
        logger.warning(f"backed[{wid}] no se pudo importar owner.py: {e}")
        return None


def start() -> None:
    """Start (in server lifespan) all backed widgets in the catalog. Idempotent. Each owner runs under its own
    supervised task in THIS loop (the voice loop) — owner start() must be cheap (lazy heavy-backend start on first
    handle), so unused widgets do not pay the cost."""
    for w in runtime.catalog():
        if (w.get("kind") or "passive") != "backed":
            continue
        wid = w.get("id") or ""
        if not wid or wid in _services:
            continue
        # Optional GATE (V2-008): a backed widget may require a brain mode (e.g. `mensajeria` only starts its v2
        # stateless owner with BRAIN=nucleo; with a direct/local baseline it falls back to the usual passive mode).
        # No gate = always. GENERAL mechanism, not a widget special case.
        gate = (w.get("backend") or {}).get("gate")
        if gate == "nucleo":
            try:
                from config.v2 import active_brain
                if active_brain() != "nucleo":
                    logger.info(f"backed[{wid}] gated a BRAIN=nucleo — omitido (brain actual distinto)")
                    continue
            except Exception:
                continue
        owner = _load_owner(wid)
        if owner is None:
            continue
        svc = _Service(wid, owner)
        svc.task = asyncio.create_task(svc._run())
        _services[wid] = svc
        logger.info(f"backed[{wid}] supervisor arrancado")


async def stop() -> None:
    """Stop all owners cleanly (lifespan finally)."""
    for wid, svc in list(_services.items()):
        if svc.task:
            svc.task.cancel()
        try:
            await svc.owner.stop()
        except Exception:
            pass
    _services.clear()


def is_backed(wid: str) -> bool:
    w = runtime.get(wid)
    return bool(w) and (w.get("kind") or "passive") == "backed"


def enqueue(wid: str, action: str, payload: dict) -> bool:
    """Leave a command in the owner mailbox. Return True if queued (backed and live widget), False otherwise (passive,
    not started, or disabled widget) → caller (server_api) falls back to the normal apply_action path."""
    svc = _services.get(wid)
    if svc is None:
        return False
    return svc.enqueue(action, payload)


def info(wid: str) -> dict:
    """Supervised owner state for a backed widget (for the FlashBrain bridge, `nucleo/flash/procs.py`). `running` =
    has a live supervised task; `disabled` = disabled after MAX_FAILS. `backed=False` if the widget is not backed /
    not under supervision."""
    svc = _services.get(wid)
    if svc is None:
        return {"backed": is_backed(wid), "running": False, "disabled": False, "fails": 0}
    return {"backed": True, "running": bool(svc.task and not svc.task.done()),
            "disabled": svc.disabled, "fails": svc.fails}


def running() -> list[str]:
    """Ids of backed widgets with a live supervised owner."""
    return [wid for wid, svc in _services.items() if svc.task and not svc.task.done() and not svc.disabled]
