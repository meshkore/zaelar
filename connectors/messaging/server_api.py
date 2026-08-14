#
# server_api.py — HTTP control API for messaging (INI-015). PROGRAMMATIC entry to connect/disconnect (control.py).
# NOTE: the WIDGET does not call this API (it cannot fetch — isolation contract); the widget enqueues the order via
# ctx.action -> data.py -> store, and the supervisor drains it and calls the same control.py. This API remains for
# programmatic/external use and for `GET /api/messaging/state` (redacted config + live state).
#
# Loopback (single-user local desktop app), like the rest of zaelar's API.
#
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import connectors as cfg
from connectors.messaging import control

router = APIRouter()


@router.get("/api/messaging/state")
async def state():
    """Per-platform state: REDACTED config (no secrets) + live link state (status/qr)."""
    from connectors.messaging import store
    live = store.load().get("platforms", {})
    out = {p: {**cfg.public(p), **(live.get(p) or {})} for p in control.PLATFORMS}
    return JSONResponse({"platforms": out})


@router.post("/api/messaging/{platform}/connect")
async def connect(platform: str, payload: dict | None = None):
    res = await control.apply_connect((platform or "").lower(), payload or {})
    code = 200 if res.get("ok") else (404 if "desconocida" in res.get("error", "") else 400)
    return JSONResponse(res, status_code=code)


@router.post("/api/messaging/{platform}/disconnect")
async def disconnect(platform: str, payload: dict | None = None):
    res = await control.apply_disconnect((platform or "").lower(), payload or {})
    return JSONResponse(res, status_code=200 if res.get("ok") else 404)
