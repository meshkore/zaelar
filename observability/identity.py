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
    return info


def end_session(reason: str = "frontend") -> dict:
    """Cierra la sesión en curso (botón de parar, pestaña cerrada). El siguiente evento abrirá una nueva sola:
    preferimos una sesión huérfana bien marcada a un evento sin sesión."""
    with _lock:
        info = dict(_session)
        _session["id"] = None
        _session["started_ms"] = None
        _session["source"] = ""
    if info.get("id"):
        dur = round(time.time() * 1000) - (info.get("started_ms") or 0)
        _emit_session("end", info, extra={"reason": (reason or "")[:40], "duration_ms": dur})
        _report_to_control_plane("end", info)
    return info


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


def _emit_session(label: str, info: dict, extra: dict | None = None) -> None:
    """Marca de sesión en el propio hilo de eventos. Import perezoso: `voice.observer` importa este módulo."""
    try:
        from voice.observer import emit
        emit("session", label, role="system",
             extra={"session_id": info.get("id"), "user_id": user_id(), **(extra or {})})
    except Exception:
        pass
