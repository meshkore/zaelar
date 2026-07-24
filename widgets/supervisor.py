#
# supervisor.py — el HOST de los widgets "backed" (kind:"backed"), diseñado en zaelar-modules.md §Widget-apps y
# construido con el navegador (INI-016, primer backed widget). Un widget "passive" (los de siempre) no tiene proceso:
# view_data lee bajo demanda y el único escritor es su propio ctx.action o Hermes. Un widget "backed" es una
# pequeña APP con backend vivo (el navegador tiene un Chromium headless por dentro): su carpeta trae un
# `owner.py` con `async start()/stop()/handle(action,payload)`, y ESTE supervisor —arrancado en el lifespan del
# server, en el MISMO loop que la voz— lo descubre en el catálogo, lo importa y lo gobierna:
#
#   • ÚNICO ESCRITOR por construcción: el owner es el único que escribe en widgets/_data/<id>/ (via store.save →
#     refresco SSE de la tarjeta abierta). La cara (data.py + widget.js) pasa a ser SOLO-LECTURA + ENCOLAR: una
#     acción del operador (ctx.action) o de Hermes ([[widget.data]]) NO toca el store, deja la orden en el BUZÓN
#     (una asyncio.Queue) que el owner drena en orden. Elimina la carrera de dos escritores por diseño, no con locks.
#   • SUPERVISIÓN: si el owner revienta, se reintenta con backoff exponencial; tras MAX_FAILS fallos seguidos se
#     DESACTIVA (degrada a último estado conocido, congelado, en vez de martillear) — un owner caído nunca puede
#     tumbar la voz ni otro widget. Todo se traza por voice/observer (kind "backed") para los testers.
#
import asyncio
import importlib
import os

from loguru import logger

from . import runtime

_MAX_FAILS = int(os.environ.get("WIDGETS_BACKED_MAX_FAILS", "4"))   # fallos seguidos de start() antes de desactivar
_QUEUE_MAX = int(os.environ.get("WIDGETS_BACKED_QUEUE", "128"))


def _emit(label: str, wid: str, text: str = "") -> None:
    """Observabilidad del ciclo de vida backed → /events + /api/debug (kind 'backed'). Nunca revienta."""
    try:
        from voice.observer import emit
        emit("backed", label, text=(f"{wid}: {text}" if text else wid), extra={"id": wid})
    except Exception:
        pass


class _Service:
    """Un widget backed vivo: su owner + su buzón + su tarea supervisada. El buzón (Queue) SOBREVIVE a los
    reinicios del owner (vive en el _Service, no dentro del _run) — un crash no pierde las órdenes ya encoladas."""

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
                while True:                                   # buzón: drena órdenes en orden, una a una
                    action, payload = await self.queue.get()
                    try:
                        await self.owner.handle(action, payload)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:                    # un fallo de UNA orden (URL mala, timeout) NO reinicia
                        _emit("cmd_error", self.wid, f"{action}: {e}")
                        logger.warning(f"backed[{self.wid}] handle {action!r} falló: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:                            # crash del owner (start o algo fatal) → reintento
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
    """Importa widgets/<id>/owner.py. Import perezoso: un owner que no importa (p.ej. falta una dep) desactiva
    SOLO ese widget, nunca el arranque del server."""
    try:
        return importlib.import_module(f"widgets.{wid}.owner")
    except Exception as e:
        _emit("import_error", wid, str(e))
        logger.warning(f"backed[{wid}] no se pudo importar owner.py: {e}")
        return None


def start() -> None:
    """Arranca (en el lifespan del server) todos los widgets backed del catálogo. Idempotente. Cada owner corre
    bajo su propia tarea supervisada en ESTE loop (el de la voz) — start() del owner debe ser barato (arranque
    perezoso del backend pesado en el primer handle), para no pagar el coste si el widget nunca se usa."""
    for w in runtime.catalog():
        if (w.get("kind") or "passive") != "backed":
            continue
        wid = w.get("id") or ""
        if not wid or wid in _services:
            continue
        # GATE opcional (V2-008): un backed widget puede exigir un modo de cerebro (p.ej. `mensajeria` solo
        # arranca su owner v2 stateless con BRAIN=nucleo; con un baseline direct/local cae al passive de siempre).
        # Sin gate = siempre. Mecanismo GENERAL, no un caso especial de un widget.
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
    """Para todos los owners limpiamente (finally del lifespan)."""
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
    """Deja una orden en el buzón del owner. Devuelve True si se encoló (widget backed y vivo), False si no
    (widget passive, no arrancado o desactivado) → el llamador (server_api) cae al camino normal de apply_action."""
    svc = _services.get(wid)
    if svc is None:
        return False
    return svc.enqueue(action, payload)


def info(wid: str) -> dict:
    """Estado del owner supervisado de un widget backed (para el bridge del FlashBrain, `nucleo/flash/procs.py`).
    `running` = tiene una tarea supervisada viva; `disabled` = desactivado tras MAX_FAILS. `backed=False` si el
    widget no es backed / no está bajo supervisión."""
    svc = _services.get(wid)
    if svc is None:
        return {"backed": is_backed(wid), "running": False, "disabled": False, "fails": 0}
    return {"backed": True, "running": bool(svc.task and not svc.task.done()),
            "disabled": svc.disabled, "fails": svc.fails}


def running() -> list[str]:
    """Ids de widgets backed con owner vivo bajo supervisión."""
    return [wid for wid, svc in _services.items() if svc.task and not svc.task.done() and not svc.disabled]
