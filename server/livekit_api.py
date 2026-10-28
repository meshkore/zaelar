#
# LiveKit HTTP: mints room-join tokens + exposes the non-secret connect config.
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
from loguru import logger
from livekit import api

from voice import screens as _screens
from voice.engine.core.config import SETTINGS

router = APIRouter()

# ── ONE LIVE VOICE SESSION PER MACHINE (2026-07-12) ─────────────────────────────────────────────────────────
# Two tabs/browsers with the mic open at the same time drive the pipeline crazy (two agents, two mics, double event
# stream). On localhost ALL connections are the SAME computer → the server arbitrates. An in-process lock with
# HEARTBEAT: the LIVE tab renews every ~4s; if another tries to start, it is denied and the UI tells it to close the
# other one. The lock expires by itself (TTL) if the live tab closes/hangs without releasing. Cross-browser because
# it is server-side (not localStorage). The tester (2nd participant) does NOT request the lock → unaffected.
_LOCK_TTL = float(os.getenv("ZAELAR_SESSION_TTL", "12"))   # s; with ~4s heartbeat, 3 misses in a row = expired
_lock_mx = threading.Lock()
_active = {"sid": None, "ts": 0.0, "dev": ""}


def _holder_changed(prev_sid, sid: str, dev: str, how: str) -> None:
    """One event when the voice changes hands, naming the surface (`dev`, from the client). Without it a phone
    that never hears the operator and a desktop tab quietly retaking the voice look the same on the timeline.

    V2-792 — the event is also the ORDER to the surface that lost it: `voice_sid` names the new holder's tab, so
    the old one stands down the moment the event lands instead of on its next heartbeat (up to 4 s with two open
    microphones). The tab id is not a secret (see `session_steal`: anyone who can reach this port can open one)."""
    if prev_sid == sid:
        return
    try:
        from voice.observer import emit
        emit("session", f"voice held by {dev or 'unknown device'}",
             extra={"src": how, "dev": dev, "voice_sid": str(sid or "")[:64]})
    except Exception as e:  # noqa: BLE001 — observability never breaks the lock
        logger.debug(f"voice holder event not emitted: {e!r}")


def _free(now: float) -> bool:
    return _active["sid"] is None or (now - _active["ts"]) > _LOCK_TTL


def speaks_for_the_mic(dev: str) -> bool:
    """Only the voice holder's surface writes the engine's microphone switch. A surface that just lost the voice
    turns its own mic off (frontend «one voice, claimed by hand»); obeying that write would mute the surface that took
    over. Unknown on either side (no holder, an older client without `dev`) keeps the old behaviour: obey."""
    now = _time.time()
    with _lock_mx:
        holder = "" if _free(now) else (_active.get("dev") or "")
    return not dev or not holder or dev == holder


@router.post("/api/session/acquire")
def session_acquire(sid: str = Body(..., embed=True), dev: str = Body("", embed=True)) -> dict:
    """Ask to become the ONLY live session. ok=True if the lock was free/expired or already yours; ok=False (held)
    if another tab/browser is live. Atomic (thread lock: sync handlers run in a threadpool)."""
    dev = dev if isinstance(dev, str) else ""
    now = _time.time()
    with _lock_mx:
        if _free(now) or _active["sid"] == sid:
            prev = _active["sid"]
            _active["sid"], _active["ts"], _active["dev"] = sid, now, dev[:40]
            _holder_changed(prev, sid, dev, "acquire")
            _screens.holder_beat(dev)
            return {"ok": True}
        return {"ok": False, "held": True}


@router.post("/api/session/heartbeat")
def session_heartbeat(payload: dict = Body(...)) -> dict:
    """Renew the lock (the live tab beats every ~4s). If it lost it but the lock is free, it retakes it; if another
    live tab owns it, ok=False → the UI must release (it lost the race).

    V2-654 — it also RE-ASSERTS the microphone switch when the beat carries `muted`. The beat is the cheapest
    place in the system to make a state self-correcting: whatever drifts between the icon and the engine is put
    back within one interval, so nobody has to remember to re-assert after a reconnect, a republished track or a
    tab regaining focus. `muted` is optional on purpose — an older client that never sends it beats exactly as
    before and simply leaves the switch where the explicit `POST /api/mic` last put it."""
    sid = str((payload or {}).get("sid") or "")
    muted = (payload or {}).get("muted")
    now = _time.time()
    with _lock_mx:
        owner = _active["sid"] == sid or _free(now)
        dev = str((payload or {}).get("dev") or "")[:40]
        if owner:
            if _active["sid"] != sid:
                _holder_changed(_active["sid"], sid, dev, "heartbeat")
            _active["sid"], _active["ts"], _active["dev"] = sid, now, dev
            _screens.holder_beat(dev)
    # Only the OWNER's beat speaks for the microphone. A tab that has just lost the voice beats once more before it
    # learns so, and its «unmuted» used to re-open the engine's mic under whoever took it (demo 2026-09-28: the
    # operator's tab, left with mic and speaker on, while the demo driver held the session).
    if owner and isinstance(muted, bool):
        from voice import mic_input
        mic_input.set_muted(muted, source="heartbeat", dev=dev)
    return {"ok": True} if owner else {"ok": False, "held": True}


@router.post("/api/session/steal")
def session_steal(sid: str = Body(..., embed=True), dev: str = Body("", embed=True)) -> dict:
    """TAKE the live-session lock from whoever holds it. An EXPLICIT operator gesture, never automatic.

    Why this exists (V2-124): the lock above is correct and its "ask, be refused, retry" loop is the right default
    — when the holder closes, the waiter gets the voice on its own. That works when both surfaces are tabs the
    operator can see. It stops working the moment the two surfaces are a PHONE and a COMPUTER IN ANOTHER ROOM:
    the phone cannot "close the other tab", so the voice is stuck wherever it happens to be and the only fix is
    walking to the laptop.

    Handing it over needs no new machinery on the loser's side: the holder's heartbeat (~4 s) already answers
    `ok:false` once someone else owns the lock, and the frontend already reacts to that by calling stop() and
    saying so on screen. So this simply writes the new owner and lets the existing mechanism do the rest —
    worst case the previous holder keeps the mic for one heartbeat interval.

    Not a security boundary and not pretending to be one: anyone who can reach this port can already open a
    session. Admission is server/ingress.py's job, and it runs before this."""
    dev = dev if isinstance(dev, str) else ""
    now = _time.time()
    with _lock_mx:
        prev = _active["sid"]
        _active["sid"], _active["ts"], _active["dev"] = sid, now, dev[:40]
    _screens.holder_beat(dev)
    _screens.touched(dev)
    _holder_changed(prev, sid, dev, "steal")
    return {"ok": True, "took_from": prev}


@router.post("/api/session/release")
def session_release(sid: str = Body(..., embed=True)) -> dict:
    """Release the lock if it is yours (when closing the tab, via sendBeacon). Idempotent."""
    with _lock_mx:
        if _active["sid"] == sid:
            _active["sid"], _active["ts"], _active["dev"] = None, 0.0, ""
            _screens.holder_released()
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


def _token_from_egress(identity: str, name: str) -> JSONResponse:
    import httpx
    try:
        from nucleo.energy import egress as llm_egress
        r = httpx.post(f"{llm_egress.root()}/livekit/token", json={"identity": identity, "name": name},
                       headers={"Authorization": f"Bearer {llm_egress.credential()}"}, timeout=10.0)
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:  # noqa: BLE001 — the browser gets a visible failure, never a token we could not sign
        return JSONResponse({"error": "token_unavailable", "detail": str(e)[:160]}, status_code=502)


@router.get("/api/token")
def token(identity: str = "operator", name: str = "You") -> JSONResponse:
    """Mint a join token for a FRESH per-session room.

    A unique room per connection guarantees automatic agent dispatch every time:
    reusing a fixed room name means a lingering/zombie agent from a previous
    session can block a new dispatch (the browser joins but no agent shows up).
    The worker's request_fnc accepts rooms prefixed with SETTINGS.room_name, so
    ``zaelar-<uuid>`` is serviced while other projects' rooms are rejected.

    Refuses while the global ⏻ switch (`nucleo.runstate`) is stopped: this is the
    ONLY place that decides whether a browser gets to open a voice session at all,
    so it's the right choke point to make "stopped" mean nothing connects, not
    just "workers are frozen once something already did". Without a token there's
    no room join, no agent dispatch, no kickoff, no observability session — instead
    of a live session appearing and getting torn down a moment later once the
    frontend's async reconciliation with the server catches up.
    """
    import uuid

    from nucleo import runstate
    if runstate.stopped():
        return JSONResponse({"error": "engine_stopped"}, status_code=409)

    # MEDIATED: the room token is signed by egress, which holds the LiveKit secret and decides the room and the agent
    # (this instance's own). A process that can sign a token can sign one for ANY room of the project — so in a
    # deployment where other people's code may run, it does not hold the secret at all.
    from nucleo.energy import egress as llm_egress
    if llm_egress.mediated():
        return _token_from_egress(identity, name)

    room = f"{SETTINGS.room_name}-{uuid.uuid4().hex[:8]}"
    grant = api.VideoGrants(
        room_join=True, room=room, can_publish=True, can_subscribe=True
    )
    tok = (
        api.AccessToken(SETTINGS.livekit_api_key, SETTINGS.livekit_api_secret)
        .with_identity(f"{identity}-{uuid.uuid4().hex[:4]}")
        .with_name(name)
        .with_grants(grant)
        .with_ttl(timedelta(hours=1))
    )
    from voice.engine.core.config import dispatch_agent_name
    if dispatch_agent_name():          # named dispatch: this engine's worker, and only it, joins the room
        tok = tok.with_room_config(api.RoomConfiguration(
            agents=[api.RoomAgentDispatch(agent_name=dispatch_agent_name())]))
    jwt = tok.to_jwt()
    return JSONResponse({"token": jwt, "url": SETTINGS.livekit_url, "room": room})
