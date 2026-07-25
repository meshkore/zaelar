#
# homeostasis.py — el LATIDO AUTÓNOMO del sistema (V2-070 «anti-degeneración»).
#
# QUÉ es: la capa que mantiene la MÁQUINA sana, como el sistema autónomo de un cuerpo (latido, respiración, curar
# una herida) — NO se piensa, se ejecuta. Es el tercer nivel, HERMANO del cerebro, nunca parte de él:
#
#     Mente        → FlashBrain (nucleo/flash)   : conduce y decide (operador + agentes). PIENSA (modelo).
#     Conciencia   → Susurro   (nucleo/susurro)  : "¿lo hago bien?" audita la CONVERSACIÓN. PIENSA (modelo).
#     Autónomo     → homeostasis (ESTE módulo)   : "¿mi CUERPO sigue sano?" mantiene la máquina. NO piensa. Cero modelo.
#
# POR QUÉ vive AQUÍ y no en el cerebro: meter reintentos/reciclados/rotación dentro del FlashBrain lo ensuciaría con
# lógica que NO es inteligencia. Igual que el latido no es una decisión consciente, esto corre solo, determinista, al
# lado — mismo patrón `start()`/`stop()` que los otros supervisores del lifespan (messaging/widgets).
#
# BINARIO (regla del operador): cada recurso tiene DOS estados, sano/degradado → curar. No 200 estados. Vigila:
#   1) MOTOR LiveKit  — el fallo del 2026-07-25: tras ~7h el worker embebido entró en bucle `wait_pc_connection
#      timed out` → el chat/voz dejó de responder. Detecta la degradación (por el LOG del SDK, señal IN-PROCESS) y,
#      si es SEGURO (voz apagada + canal inactivo), RECICLA el worker embebido; si no es seguro, avisa al operador.
#   2) LOGS           — timeline-latest.jsonl / meshkore.jsonl crecen sin límite → rota por rename (ambos abren "a"
#      por escritura, el siguiente append recrea el fichero → seguro) y poda archivos viejos.
#   3) CÁPSULAS       — el estado de relación por peer (sys_kv `capsule:*`) crece con cada agente muerto → evicta las
#      concluidas y viejas, y acota el total.
#
# INVARIANTES: NUNCA toca el FlashBrain ni la memoria del operador. Determinista, sin LLM. Fail-open DURO (un fallo
# del propio mantenimiento jamás tumba la voz/chat). Observabilidad TOTAL (evento `homeostasis` en el timeline).
# Kill-switch de 1ª clase (`ZAELAR_HOMEOSTASIS=0`). Reciclar solo cuando es seguro; si no, avisar, no romper.
#
from __future__ import annotations

import asyncio
import logging
import os
import time

log = logging.getLogger(__name__)

# ── config (infra, no UI — env-overridable para power-user/tests) ───────────────────────────────────────────────
_PERIOD_S = float(os.getenv("HOMEOSTASIS_PERIOD_S", "60"))       # cada cuánto late el chequeo

_LK_WINDOW_S = float(os.getenv("HOMEOSTASIS_LK_WINDOW_S", "180"))    # ventana para contar degradación del motor
_LK_THRESHOLD = int(os.getenv("HOMEOSTASIS_LK_THRESHOLD", "3"))      # nº de marcas en la ventana = degradado
_IDLE_S = float(os.getenv("HOMEOSTASIS_IDLE_S", "120"))             # canal inactivo si no hay timeline en N s
_RECYCLE_COOLDOWN_S = float(os.getenv("HOMEOSTASIS_RECYCLE_COOLDOWN_S", "600"))  # no reciclar más de 1×/10min

_LOG_CAP_BYTES = int(os.getenv("HOMEOSTASIS_LOG_CAP_BYTES", str(64 * 1024 * 1024)))  # 64 MB
_LOG_KEEP = int(os.getenv("HOMEOSTASIS_LOG_KEEP", "3"))             # nº de archivos rotados a conservar

_CAP_MAX = int(os.getenv("HOMEOSTASIS_CAPSULE_MAX", "200"))         # tope de cápsulas vivas
_CAP_TTL_S = float(os.getenv("HOMEOSTASIS_CAPSULE_TTL_S", str(30 * 24 * 3600)))  # concluida+vieja → evict (30d)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOG_DIR = os.getenv("ZAELAR_LOG_DIR") or os.path.join(_REPO_ROOT, ".meshkore", "logs")
_ROTATABLE = ("timeline-latest.jsonl", "meshkore.jsonl")

# marcas de degradación del motor LiveKit (timestamps), pobladas por el watcher de logging IN-PROCESS
_marks: list[float] = []
_last_recycle: float = 0.0
_alerted: set[str] = set()      # dedup de avisos al operador (una vez por incidente)


def enabled() -> bool:
    return os.getenv("ZAELAR_HOMEOSTASIS", "1").lower() not in ("0", "false", "off", "no")


# ── DETECCIÓN del motor LiveKit — señal IN-PROCESS por el logging del SDK ───────────────────────────────────────
_MARKERS = ("wait_pc_connection timed out", "entrypoint did not exit")


class _LKWatcher(logging.Handler):
    """Escucha el logger `livekit` (y sus hijos, por propagación): cada vez que el SDK loguea una señal de motor
    degradado, estampa la marca. Coste ínfimo (substring sobre el mensaje ya formateado). No emite nada."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage().lower()
        except Exception:
            return
        if any(m in msg for m in _MARKERS):
            _marks.append(time.time())
            if len(_marks) > 256:          # acota memoria (sonda, no historial)
                del _marks[:128]


_watcher = _LKWatcher()
_watcher.setLevel(logging.WARNING)


# ── funciones PURAS (testeables sin server, sin IO) ─────────────────────────────────────────────────────────────
def livekit_degraded(marks: list[float], now: float, *, window_s: float = _LK_WINDOW_S,
                     threshold: int = _LK_THRESHOLD) -> bool:
    """El motor está degradado si acumuló >= `threshold` señales de bucle WebRTC en la última ventana."""
    recent = [t for t in marks if now - t <= window_s]
    return len(recent) >= threshold


def safe_to_recycle(voice_on: bool, last_activity_ts: float, now: float, *, idle_s: float = _IDLE_S) -> bool:
    """Reciclar el motor solo si NO hay voz viva y el canal lleva `idle_s` sin actividad — así un reinicio del
    worker nunca corta una conversación en curso (regla del operador). Con voz/canal activos: avisar, no tocar."""
    if voice_on:
        return False
    return (now - last_activity_ts) >= idle_s


def capsules_to_evict(items: list[tuple[str, dict]], now: float, *, max_count: int = _CAP_MAX,
                      ttl_s: float = _CAP_TTL_S) -> list[str]:
    """Qué cápsulas (clave, cap) evictar: (a) las CONCLUIDAS (fase cierre) y viejas (updated < now-ttl); (b) si tras
    eso siguen sobrando sobre el tope, las MÁS VIEJAS por `updated` hasta cuadrar. Determinista, sin abrir la BD."""
    stale = set()
    for key, cap in items:
        phase = (cap.get("phase") or "").lower()
        updated = float(cap.get("updated") or 0)
        if phase == "cierre" and (now - updated) >= ttl_s:
            stale.add(key)
    survivors = [(k, c) for k, c in items if k not in stale]
    over = len(survivors) - max_count
    if over > 0:
        survivors.sort(key=lambda kc: float(kc[1].get("updated") or 0))   # más viejas primero
        stale.update(k for k, _ in survivors[:over])
    # preserva el orden de entrada para una salida estable
    return [k for k, _ in items if k in stale]


def logs_to_rotate(sizes: list[tuple[str, int]], *, cap_bytes: int = _LOG_CAP_BYTES) -> list[str]:
    """Qué logs rotar: los que superan el tope de tamaño."""
    return [path for path, size in sizes if size > cap_bytes]


# ── heals (IO; fail-open cada uno) ──────────────────────────────────────────────────────────────────────────────
def _emit(label: str, text: str = "", extra: dict | None = None) -> None:
    try:
        from voice import observer
        observer.emit("homeostasis", label, text, extra=extra or {})
    except Exception:
        pass


async def _alert(key: str, title: str, text: str) -> None:
    """Avisa al operador UNA vez por incidente (voz + UI + chat, sin toasts). Dedup por `key`."""
    if key in _alerted:
        return
    _alerted.add(key)
    _emit("alert", f"{title}: {text}")
    try:
        from voice import proactive
        await proactive.notify(title, text, speak=proactive.has_voice(), kind="homeostasis")
    except Exception:
        pass


def _recent_activity_ts() -> float:
    """Última señal de actividad del canal: mtime del timeline (voz/chat/cluster escriben ahí). 0 si no hay."""
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


async def _recycle_livekit(app) -> bool:
    """Recrea el worker LiveKit EMBEBIDO (aclose + make_server + nueva task) SIN reiniciar el proceso — clava el
    fallo del 2026-07-25 sin cortar el server. Devuelve True si recicló."""
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
        _marks.clear()                       # borrón y cuenta nueva: la ventana de degradación se reinicia
        _emit("recycle", "motor LiveKit reciclado (worker embebido re-registrado)")
        log.info("homeostasis: motor LiveKit reciclado")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("homeostasis: reciclado del motor falló: %s", e)
        return False


def _rotate_log(path: str, *, keep: int = _LOG_KEEP) -> None:
    """Rota un log por rename (seguro: el writer abre en 'a' por escritura → el siguiente append recrea el fichero)
    y poda los archivos rotados más viejos, conservando `keep`."""
    try:
        if not os.path.exists(path):
            return
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        os.rename(path, f"{path}.{stamp}")
        _emit("rotate", f"{os.path.basename(path)} rotado ({stamp})")
        # poda: conserva los `keep` más recientes de los rotados de ESTE fichero
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


# ── el LATIDO ───────────────────────────────────────────────────────────────────────────────────────────────────
async def _tick(app) -> None:
    """Un latido: los tres chequeos, cada uno aislado (un fallo no frena a los otros)."""
    now = time.time()

    # 1) MOTOR LiveKit
    try:
        if getattr(app, "state", None) is not None and getattr(app.state, "lk_server", None) is not None:
            if livekit_degraded(_marks, now):
                if now - _last_recycle < _RECYCLE_COOLDOWN_S:
                    pass  # ya se recicló hace poco; deja respirar (evita un bucle de reciclado)
                elif safe_to_recycle(_voice_on(), _recent_activity_ts(), now):
                    _emit("degraded", "motor LiveKit degradado (bucle WebRTC) — reciclando en frío")
                    ok = await _recycle_livekit(app)
                    if ok:
                        _alerted.discard("lk_degraded")  # rearmar el aviso para un futuro incidente distinto
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

    # 3) CÁPSULAS
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
    # un primer latido tras un respiro (deja que el arranque asiente), luego periódico
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
    """Arranca el latido (idempotente). Se llama en el lifespan del server, hermano de los otros supervisores."""
    global _task
    if not enabled():
        log.info("homeostasis: apagado por ZAELAR_HOMEOSTASIS")
        return
    if _task and not _task.done():
        return
    logging.getLogger("livekit").addHandler(_watcher)   # sonda IN-PROCESS del motor
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
