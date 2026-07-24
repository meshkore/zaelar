#
# LiveKit control-plane HTTP (INI-012): mints room-join tokens + exposes the non-secret connect config.
#
# Audio NEVER flows through here — it rides WebRTC directly between the browser and the LiveKit server. This
# process just hands the browser a short-lived JWT + the LiveKit ws URL + room name, and the browser's LiveKit
# client SDK joins the room where the embedded agent worker (server lifespan) is already waiting.
#
# Mounted ONLY when ZAELAR_ENGINE=livekit (server/__init__.py) so the legacy Pipecat path is untouched.
#
from __future__ import annotations

import os
import threading
import time as _time
from datetime import timedelta

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse
from livekit import api

from voice.engine.core.config import SETTINGS

router = APIRouter()

# ── UNA SOLA SESIÓN DE VOZ VIVA POR MÁQUINA (2026-07-12) ────────────────────────────────────────────────────
# Dos pestañas/navegadores con el micro abierto a la vez vuelven loco el pipeline (dos agentes, dos micros, doble
# stream de eventos). En localhost TODAS las conexiones son el MISMO ordenador → el server es el árbitro. Un lock
# in-process con LATIDO: la pestaña VIVA renueva cada ~4s; si otra intenta arrancar, se le niega y la UI le dice
# "ciérralo para usarlo aquí". El lock caduca solo (TTL) si la pestaña viva se cierra/cuelga sin soltar. Cross-browser
# porque es server-side (no localStorage). El tester (2º participante) NO pide lock → no le afecta.
_LOCK_TTL = float(os.getenv("ZAELAR_SESSION_TTL", "12"))   # s; con latido ~4s, 3 fallos seguidos = caducado
_lock_mx = threading.Lock()
_active = {"sid": None, "ts": 0.0}


def _free(now: float) -> bool:
    return _active["sid"] is None or (now - _active["ts"]) > _LOCK_TTL


@router.post("/api/session/acquire")
def session_acquire(sid: str = Body(..., embed=True)) -> dict:
    """Pide ser la ÚNICA sesión viva. ok=True si el lock estaba libre/caducado o ya es tuyo; ok=False (held) si
    otra pestaña/navegador está viva. Atómico (lock de hilos: los handlers sync corren en un threadpool)."""
    now = _time.time()
    with _lock_mx:
        if _free(now) or _active["sid"] == sid:
            _active["sid"], _active["ts"] = sid, now
            return {"ok": True}
        return {"ok": False, "held": True}


@router.post("/api/session/heartbeat")
def session_heartbeat(sid: str = Body(..., embed=True)) -> dict:
    """Renueva el lock (la pestaña viva late cada ~4s). Si lo perdió pero está libre, lo re-toma; si lo tiene otra
    viva, ok=False → la UI debe soltar (perdió la carrera)."""
    now = _time.time()
    with _lock_mx:
        if _active["sid"] == sid or _free(now):
            _active["sid"], _active["ts"] = sid, now
            return {"ok": True}
        return {"ok": False, "held": True}


@router.post("/api/session/release")
def session_release(sid: str = Body(..., embed=True)) -> dict:
    """Suelta el lock si es tuyo (al cerrar la pestaña, vía sendBeacon). Idempotente."""
    with _lock_mx:
        if _active["sid"] == sid:
            _active["sid"], _active["ts"] = None, 0.0
    return {"ok": True}

# Engine switch WITHOUT a build step or touching the 6 static importers of session.js: on the LiveKit engine we
# serve the LiveKit adapter (session-lk.js) AT the session.js URL. This explicit route is registered before the
# /static mount, so it wins; in Pipecat mode this router isn't mounted and the real session.js is served as usual.
_FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "app", "services")


@router.get("/static/app/services/session.js")
def session_module() -> FileResponse:
    return FileResponse(os.path.join(_FRONTEND, "session-lk.js"),
                        media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/api/livekit")
def livekit_config() -> dict:
    """Non-secret config the browser needs to connect (URL + room + which providers are live)."""
    stt_device = None
    if SETTINGS.stt_provider == "whisper_local":
        from voice.engine.core import accel
        stt_device = accel.pick_device(SETTINGS.whisper_device)  # predicted (same machine)
    return {
        "livekitUrl": SETTINGS.livekit_url,
        "room": SETTINGS.room_name,
        "profile": SETTINGS.profile,
        "stt": SETTINGS.stt_provider,
        "sttDevice": stt_device,
        "tts": SETTINGS.tts_provider,
        "llmProvider": SETTINGS.llm_provider,
    }


@router.get("/api/token")
def token(identity: str = "operator", name: str = "You") -> JSONResponse:
    """Mint a join token for a FRESH per-session room.

    A unique room per connection guarantees automatic agent dispatch every time:
    reusing a fixed room name means a lingering/zombie agent from a previous
    session can block a new dispatch (the browser joins but no agent shows up).
    The worker's request_fnc accepts rooms prefixed with SETTINGS.room_name, so
    ``zaelar-<uuid>`` is serviced while other projects' rooms are rejected.
    """
    import uuid

    room = f"{SETTINGS.room_name}-{uuid.uuid4().hex[:8]}"
    grant = api.VideoGrants(
        room_join=True, room=room, can_publish=True, can_subscribe=True
    )
    jwt = (
        api.AccessToken(SETTINGS.livekit_api_key, SETTINGS.livekit_api_secret)
        .with_identity(f"{identity}-{uuid.uuid4().hex[:4]}")
        .with_name(name)
        .with_grants(grant)
        .with_ttl(timedelta(hours=1))
        .to_jwt()
    )
    return JSONResponse({"token": jwt, "url": SETTINGS.livekit_url, "room": room})
