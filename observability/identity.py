"""
observability.identity — QUIÉN y CUÁNDO: el usuario de esta instalación y la sesión de trabajo en curso.

Los eventos ya sabían QUÉ pasó (`kind`), de qué PIEZA (`cat`) y de qué FLUJO (`trace`/correlation id). Les
faltaban los dos ejes que permiten analizar el uso REAL:

- **`user_id`** — estable de por vida para esta instalación. Se genera un **UUID4 aleatorio** la primera vez y se
  persiste. Aleatorio y no correlativo a propósito: no identifica a nadie por sí mismo y no puede colisionar con
  el de otra instalación. Si el entorno ya trae uno (`ZAELAR_USER_ID`), manda ese — la identidad la puede fijar
  quien despliega, y este módulo no necesita saber por qué.
- **`session_id`** — un UUID4 por SESIÓN DE TRABAJO: desde que el operador arranca el agente hasta que cierra el
  navegador o le da al botón de parar. No es el proceso (el server puede vivir semanas) ni el turno (dura
  segundos): es el tramo de trabajo que el operador reconocería como «lo de esta tarde».

**Dónde vive cada cosa, y por qué:** el `user_id` va a un JSON en `config/` (gitignored) y NO a la base de
datos, a propósito — un `reset` con «borrar memoria» destruye `zaelar.db`, y perder la identidad de la
instalación cada vez que alguien limpia su memoria haría inútil cualquier análisis longitudinal. La sesión, al
revés, es efímera por definición y vive en RAM.

Todo es defensivo: si el fichero no se puede leer o escribir, se devuelve un id de proceso en memoria. Un fallo
de observabilidad NUNCA puede tumbar un turno.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from loguru import logger

from nucleo import workspace as _workspace

_lock = threading.Lock()
_user: dict = {"id": None}
_session: dict = {"id": None, "started_ms": None, "source": ""}

# Techo de INACTIVIDAD REAL (operador, 2026-08-13): sin esto una sesión vive en RAM hasta que ⏻/pestaña la
# cierren EXPLÍCITAMENTE, y si esa señal no llega (red cortada, pestaña matada sin `pagehide`) sigue viva para
# siempre, acumulando eventos de tramos de trabajo que no tienen nada que ver entre sí. Red de seguridad, no
# sustituye al cierre explícito — solo actúa cuando ese cierre no llegó.
IDLE_TIMEOUT_MS = int(os.getenv("ZAELAR_SESSION_IDLE_MIN", "5")) * 60_000
_last_real_activity_ms: dict = {"v": None}

# HEARTBEAT to the control-plane (2026-08-15, operator's proposal). The explicit session close
# (`_report_to_control_plane("end", ...)`) is best-effort: if the Machine dies hard (OOM, `kill -9`) it never
# arrives, and the backoffice (`cloud/backoffice/src/flyQuery.js`) had to GUESS "is this account still alive?"
# from the timestamp of the most recent event in the account's own SQLite — a 60s window polluted by background
# noise (homeostasis/cron), not a signal designed for this. No need to invent anything: the same "start" report
# already sent on open (`_report_to_control_plane`) already touches `last_seen_at` on the control-plane
# (`userSessions.touch`, idempotent — no new row, no `energy`/`events` duplication with `energy=0`). Repeating
# it every `_HEARTBEAT_INTERVAL_S` while the session stays open gives that mark the precision it was missing,
# with no new verb on the control-plane. Still a total no-op on a local install without
# `CONTROL_PLANE_URL`/`ZAELAR_USER_ID` (same guard as `_report_to_control_plane`) — one single piece of code
# serves both the self-hosted engine and the one deployed on Fly. Do NOT confuse this with the 4s heartbeat in
# `server/livekit_api.py` (an in-memory "one tab per machine" lock, no control-plane involved).
_HEARTBEAT_INTERVAL_S = float(os.getenv("ZAELAR_SESSION_HEARTBEAT_S", "15"))
_heartbeat: dict = {"task": None}


def _identity_file() -> Path:
    return _workspace.root() / "config" / "identity.json"


def user_id() -> str:
    """El id ESTABLE de esta instalación: el que traiga el entorno si lo hay, o un UUID4 propio persistido."""
    from nucleo import cloud_account

    provided = cloud_account.my_user_id()
    if provided:
        return provided
    if _user["id"]:
        return _user["id"]
    with _lock:
        if _user["id"]:
            return _user["id"]
        p = _identity_file()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            uid = str(data.get("user_id") or "").strip()
        except Exception:
            uid = ""
        if not uid:
            uid = str(uuid.uuid4())
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".json.tmp")
                tmp.write_text(json.dumps({"user_id": uid, "created_ms": round(time.time() * 1000)},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, p)          # atómico: un corte a media escritura no deja un fichero corrupto
            except Exception:
                pass                        # sin disco escribible seguimos con un id de proceso, no rompemos nada
        _user["id"] = uid
        return uid


def session_id() -> str:
    """La sesión de trabajo EN CURSO. Se abre sola en el primer uso — un evento nunca queda sin sesión."""
    if _session["id"]:
        return _session["id"]
    with _lock:
        if not _session["id"]:
            _session["id"] = str(uuid.uuid4())
            _session["started_ms"] = round(time.time() * 1000)
            _session["source"] = _session["source"] or "auto"
    return _session["id"]


def begin_session(source: str = "frontend", force: bool = False) -> dict:
    """Abre la sesión de trabajo. **Reutiliza la que ya esté abierta** salvo `force`: el frontend llama a esto
    cada vez que conecta, y una reconexión por un bache de red o un `/reset` ligero NO es una sesión nueva —
    partirla en dos falsearía cualquier análisis de «cuánto duró y qué hizo». Una sesión nueva nace solo cuando
    la anterior se CERRÓ de verdad (⏻ o pestaña cerrada), que es justo cuando no hay ninguna abierta."""
    with _lock:
        if _session["id"] and not force:
            return dict(_session)
        _session["id"] = str(uuid.uuid4())
        _session["started_ms"] = round(time.time() * 1000)
        _session["source"] = (source or "frontend")[:40]
        info = dict(_session)
    _emit_session("start", info, extra={"source": info["source"]})
    _report_to_control_plane("start", info)
    _start_heartbeat(info)
    return info


def end_session(reason: str = "frontend") -> dict:
    """Cierra la sesión en curso (botón de parar, pestaña cerrada). El siguiente evento abrirá una nueva sola:
    preferimos una sesión huérfana bien marcada a un evento sin sesión."""
    with _lock:
        info = dict(_session)
        _session["id"] = None
        _session["started_ms"] = None
        _session["source"] = ""
    _stop_heartbeat()
    if info.get("id"):
        dur = round(time.time() * 1000) - (info.get("started_ms") or 0)
        _emit_session("end", info, extra={"reason": (reason or "")[:40], "duration_ms": dur})
        _report_to_control_plane("end", info)
        _bill_transport(dur)
    return info


# Real-time transport (LiveKit) is billed per PARTICIPANT-minute and a voice session has TWO of them
# (the operator and the agent), so the session's wall-clock is doubled here. It is charged per SESSION
# rather than per turn because the room is up — and billing — during the silences between turns too,
# which is exactly the part no per-turn hook would ever see.
#
# Only the duration crosses this seam: whether that costs anything, and how much, is the tariff's
# business (`nucleo/energy_tariffs.py` — it may legitimately be zero while the deployment sits inside
# LiveKit's included quota). Failing to bill must never break closing a session, hence the guard.
_TRANSPORT_PARTICIPANTS = 2


def _bill_transport(duration_ms: int) -> None:
    if duration_ms <= 0:
        return
    try:
        from nucleo import energy_meter
        energy_meter.report_transport_usage(
            participant_seconds=(duration_ms / 1000.0) * _TRANSPORT_PARTICIPANTS)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"identity: could not bill the transport for this session: {e}")


def note_real_activity() -> None:
    """Marca que ha habido actividad REAL (voz/worker/memoria/widget — nunca ruido de fondo como homeostasis/
    pulso/cron). Si la sesión abierta lleva más de `IDLE_TIMEOUT_MS` sin ninguna, la CIERRA (mismo camino que ⏻,
    reporta `end_session('idle_timeout')` al timeline y al control-plane) y la deja cerrada: el siguiente
    `session_id()` abrirá una nueva sola. Solo la actividad REAL cuenta para el reloj — si el pulso lo extendiera,
    una máquina viva pero sin uso jamás rotaría; si el pulso pudiera disparar la rotación, una máquina inactiva
    rotaría en cada tick del pulso. Con este filtro: ni una cosa ni la otra — solo el hueco real importa."""
    now = round(time.time() * 1000)
    with _lock:
        last = _last_real_activity_ms["v"]
        idle = bool(_session["id"] and last is not None and (now - last) > IDLE_TIMEOUT_MS)
        _last_real_activity_ms["v"] = now
    if idle:
        end_session("idle_timeout")


def session_info() -> dict:
    sid = _session["id"]
    return {"session_id": sid, "started_ms": _session["started_ms"], "source": _session["source"],
            "user_id": user_id()}


def _report_to_control_plane(label: str, info: dict) -> None:
    """Aviso opcional a un servicio de registro externo de que una sesión empieza o acaba, cuando el despliegue
    tiene uno configurado (`CONTROL_PLANE_URL` + un `ZAELAR_USER_ID`). **En una instalación normal esto es un
    no-op**: sin esas variables no se contacta con nada y no sale un solo byte de la máquina.

    Mismo contrato guarded-until-configured que `nucleo/energy_meter.py`: fire-and-forget, y un fallo NUNCA puede
    tumbar el arranque ni el cierre de una sesión. No viaja ningún evento ni ninguna transcripción — solo
    `(user_id, session_id, start|end)`."""

    try:
        import asyncio
        import os

        from nucleo import cloud_account

        url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
        uid = cloud_account.my_user_id()
        if not url or not uid:
            return

        async def _post() -> None:
            import httpx
            token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(url.rstrip("/") + "/session",
                                      json={"user_id": uid, "session_id": info.get("id"), "event": label},
                                      headers={"X-Service-Token": token} if token else {})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"observability: reporte de sesión '{label}' falló (no fatal): {e}")

        asyncio.get_running_loop()
        asyncio.create_task(_post())
    except RuntimeError:
        pass          # sin loop (arranque, test) — el registro de actividad no vale una excepción
    except Exception:
        pass


async def _heartbeat_loop(info: dict) -> None:
    """Repeats the "start" report every `_HEARTBEAT_INTERVAL_S` while the session stays alive — see the
    `_heartbeat`/`_HEARTBEAT_INTERVAL_S` comment above. `_report_to_control_plane` is already a no-op when
    unconfigured, so this loop costs nothing on a local install: it just sleeps and sends not a single byte."""
    import asyncio
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
            _report_to_control_plane("start", info)
    except asyncio.CancelledError:
        pass


def _start_heartbeat(info: dict) -> None:
    _stop_heartbeat()
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        _heartbeat["task"] = loop.create_task(_heartbeat_loop(info))
    except RuntimeError:
        pass          # no loop (startup, a test) — no heartbeat to launch, and none needed


def _stop_heartbeat() -> None:
    t = _heartbeat["task"]
    if t is not None:
        t.cancel()
    _heartbeat["task"] = None


def _emit_session(label: str, info: dict, extra: dict | None = None) -> None:
    """Marca de sesión en el propio hilo de eventos. Import perezoso: `voice.observer` importa este módulo."""
    try:
        from voice.observer import emit
        emit("session", label, role="system",
             extra={"session_id": info.get("id"), "user_id": user_id(), **(extra or {})})
    except Exception:
        pass
