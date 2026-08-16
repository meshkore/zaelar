"""nucleo/runstate.py — ¿ESTÁ EL AGENTE EN MARCHA O PARADO? La verdad ÚNICA, del lado del servidor (V2-092).

## El fallo que corrige

El botón ⏻ existía desde V2-039 y desde V2-065 ya congelaba los Brain Workers (SIGSTOP), pero su estado vivía
SOLO en el `localStorage` del navegador (`hb_power_off`). Consecuencias reales, reportadas por el operador con el
agente PARADO delante:

  - Un vídeo de YouTube seguía reproduciéndose, y al RECARGAR la página volvía a arrancar solo (su estado
    persistido decía «reproduciendo» y su `<iframe>` nace con `autoplay=1`).
  - La música sonaba AL MISMO TIEMPO que el vídeo — dos widgets peleándose por el altavoz.
  - Los `tick()` de background seguían corriendo: un agente «parado» que seguía sondeando conectores.

O sea: el ⏻ paraba la VOZ y los WORKERS, y nada más. Lo demás ni se enteraba, porque no había a quién preguntar:
el servidor no sabía que el operador había parado el agente. Un estado que gobierna todo el sistema no puede vivir
en un `localStorage` — es per-navegador, per-origen, y el backend (widgets, background, crons, la nube) no lo ve.

## El modelo

**Un solo interruptor, en el servidor, persistido** (`sys_kv`, sobrevive a un reinicio del motor porque es una
INTENCIÓN del operador, no un estado de proceso). Todo lo que puede «estar en marcha» lo consulta o lo recibe:

    PARAR  →  workers CONGELADOS (SIGSTOP, reversible) · widgets productores SUSPENDIDOS · background sin ticks
              · crons que no disparan · nada nuevo se arranca · SESIÓN DE OBSERVABILIDAD CERRADA (2026-08-16)
    ARRANCAR → workers CONTINÚAN donde estaban · background vuelve · crons vuelven
              · **los widgets NO se reanudan** (decisión explícita del operador, ver abajo)

**Asimetría deliberada.** Parar es total; arrancar NO resucita la reproducción. Palabras del operador
(2026-08-13): «si digo que arranque el sistema no necesariamente hay que volver a arrancar los widgets, que ya sea
el usuario a mano el que decide si quiere volver a seguir escuchando música o un podcast o reproduciendo un
vídeo». Lo que SÍ debe continuar es el TRABAJO: un Brain Worker a mitad de crear un widget o de una búsqueda
compleja se congela y sigue exactamente donde estaba. La diferencia es quién es el dueño de la intención: la
música la puso el operador para él, la tarea la encargó y espera su resultado.

## Frontera

Este módulo NO sabe pausar nada: sabe QUIÉN hay que avisar y en qué orden. El cómo vive en su dueño
(`dispatch.pause_all` para los workers, `widgets/producers.py` para el canvas, `widgets/background.py` para los
ciclos). Así una pieza nueva que pueda «estar en marcha» se engancha aquí en una línea y no reimplementa la
política.
"""
from __future__ import annotations

import time

from loguru import logger

RUNNING = "running"
STOPPED = "stopped"

_KV_KEY = "run:state"

# Caché en proceso: `stopped()` lo consultan caminos CALIENTES (cada acción de widget, cada tick de background),
# y no puede costar una lectura de SQLite cada vez. El `sys_kv` es el respaldo durable, no la fuente de cada
# lectura: este proceso es el único que escribe el interruptor.
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
        d = memory.kv_get(_KV_KEY)          # kv_get/kv_set ya hacen el JSON: se guarda el dict tal cual
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
        # Un fallo de persistencia NO puede impedir la parada: el interruptor en memoria ya está puesto y todo el
        # sistema lo obedece YA. Lo único que se pierde es sobrevivir a un reinicio del motor.
        logger.warning(f"runstate: el estado no se pudo persistir ({e!r}) — vale para esta ejecución")


def state() -> str:
    """`"running"` | `"stopped"`. Nunca lanza: ante cualquier duda, «en marcha» (un fallo de lectura no puede
    dejar al operador con un agente que se niega a trabajar)."""
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
    """PARA EL AGENTE de verdad. Congela a todo el que pueda estar trabajando o produciendo, en un orden que
    importa:

    1. **El interruptor primero.** Mientras se para todo lo demás pueden llegar acciones nuevas; con el flag ya
       puesto, el embudo de acciones (`widgets/server_api.py`) las rechaza en vez de arrancar algo justo detrás
       de la parada.
    2. **La sesión de observabilidad se cierra** (2026-08-16, hallazgo real: con el agente parado y el navegador
       abierto, el ruido de fondo —pulso ~1Hz, proyección de estado— seguía llegando a la sesión que ya estaba
       abierta y la mantenía «EN CURSO» para siempre en el master, con sus flujos creciendo). `end_session` emite
       su propio evento `system` de cierre —`stamp_identity` solo LEE la sesión para esa categoría, nunca la
       reabre— así que lo que llegue DESPUÉS de parar queda sin sesión, tal como debe ser una parada deliberada.
    3. **Workers** (SIGSTOP, reversible) — congelados en el sitio exacto, no muertos.
    4. **Widgets productores** — cada uno por su acción declarada de suspensión (ver `widgets/producers.py`).

    Idempotente: parar dos veces no rompe nada (una sesión ya cerrada no tiene nada que cerrar). Nunca lanza —
    cada paso está aislado, porque una parada a medias es peor que ninguna: el operador cree que paró y algo
    sigue sonando."""
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
    """ARRANCA EL AGENTE. Continúa el TRABAJO congelado (SIGCONT) y vuelve a permitir background/crons/acciones.

    **NO reanuda los widgets a propósito** — ver la asimetría documentada arriba. Volver a poner la música es un
    gesto del operador, no una consecuencia de encender.

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
    logger.info(f"runstate: EN MARCHA por {src} — {resumed} worker(s) continúan donde estaban "
                f"(los widgets NO se reanudan: los reanuda el operador)")
    _emit("start", f"en marcha por {src}: {resumed} worker(s) continúan", {"src": src, "workers": resumed})
    return {"ok": True, "state": RUNNING, "workers": resumed}


def _reset_for_tests() -> None:
    """Tests only: forgets the in-process cache so the next `state()` re-reads `sys_kv`, and clears any turn in
    flight / deferred stop a previous test left half-done."""
    _state.update({"value": None, "at": 0.0, "src": ""})
    _inflight.update({"n": 0})
    _pending.update({"stop": False, "src": ""})
