"""server_api.py — control plane for the photos connector (V2-564), at `/api/photos/*`.

Checked free first (`grep -rn '"/api/photos' server/ connectors/`) — nothing else in this repo answers that
prefix.

status · connect · callback · disconnect are the shared account flow (`connectors/oauth_routes.py`), with one
fixed provider. `connect` starts the ACCOUNT-level consent (the `photospicker` scope); it is NOT the
per-session picker — that starts later, from INSIDE the widget's own `apply_action("connect")` (a direct
Python call to `service.start_session()`, never HTTP), the moment the operator actually wants to pick photos
rather than merely authorize the app once. `disconnect` also drops any pending picker session. Its own:

  · `GET /api/photos/poll` — check/import a pending picker session (the widget's background tick calls this).
  · `GET /api/photos/thumb/{item_id}` — the cached thumbnail JPEG for one imported item. This is the ONE
    place a `<img src=...>` in `widget.js` is allowed to point at: it is same-origin, served by US, and
    never Google's own signed (and short-lived) `baseUrl`.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from connectors.oauth_routes import Door, register
from connectors.photos import oauth, providers, service, store

router = APIRouter()

DOOR = Door(prefix="/api/photos", family="fotos", oauth=oauth, providers=providers,
            status=lambda: service.status(), label="Google Photos",
            provider=service.PROVIDER_ID, forget=lambda: service.disconnect(),
            done="You can now pick your photos from the zaelar card.", done_key="oauth.photos.done")
status, connect, callback, disconnect = register(router, DOOR)
_page = DOOR.page


@router.get("/api/photos/poll")
async def poll():
    return JSONResponse(service.poll_session())


@router.get("/api/photos/thumb/{item_id}")
async def thumb(item_id: str):
    p = store.thumb_path(item_id)
    if not p.exists():
        return JSONResponse({"ok": False, "error": "sin miniatura"}, status_code=404)
    return FileResponse(str(p), media_type="image/jpeg")
