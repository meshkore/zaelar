#
# server_api.py — API HTTP de control de mensajería (INI-015). Entrada PROGRAMÁTICA al connect/disconnect
# (control.py). NOTA: el WIDGET no llama a esta API (no puede hacer fetch — contrato de aislamiento); el widget
# encola la orden por ctx.action → data.py → store, y el supervisor la drena y llama al mismo control.py. Esta API
# queda para uso programático/externo y para `GET /api/messaging/state` (config redactada + estado vivo).
#
# Loopback (app de escritorio local single-user), como el resto de la API de zaelar.
#
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import connectors as cfg
from connectors.messaging import control

router = APIRouter()


@router.get("/api/messaging/state")
async def state():
    """Estado por plataforma: config REDACTADA (sin secretos) + estado de vínculo vivo (status/qr)."""
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
