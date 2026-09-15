"""server_api.py — control plane for the photos connector (V2-564), at `/api/photos/*`.

Checked free first (`grep -rn '"/api/photos' server/ connectors/`) — nothing else in this repo answers that
prefix.

  1. `POST /api/photos/connect {client_id[, client_secret]}` — stores the OAuth app credentials and starts
     the ACCOUNT-level consent (the `photospicker` scope). Returns {ok, url}; ⚙ → Conectores opens it in a
     window. This is NOT the per-session picker — that starts later, from INSIDE the widget's own
     `apply_action("connect")` (a direct Python call to `service.start_session()`, never HTTP), the moment the
     operator actually wants to pick photos rather than merely authorize the app once.
  2. `GET /api/photos/callback?code&state` — the provider redirects back HERE after the OAuth consent (the
     account-level authorization; picking photos happens in Google's own picker UI afterward).
  3. `GET /api/photos/status` — connected? app registered? a session pending? how many photos imported.
  4. `GET /api/photos/poll` — check/import a pending picker session (the widget's background tick calls this).
  5. `POST /api/photos/disconnect` — forgets the tokens and any pending session.
  6. `GET /api/photos/thumb/{item_id}` — the cached thumbnail JPEG for one imported item. This is the ONE
     place a `<img src=...>` in `widget.js` is allowed to point at: it is same-origin, served by US, and
     never Google's own signed (and short-lived) `baseUrl`.

Loopback, like the rest of the local API.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from connectors.photos import oauth, providers, service, store

router = APIRouter()


@router.get("/api/photos/status")
async def status():
    st = service.status()
    st["catalog"] = providers.public_list()
    return JSONResponse(st)


@router.post("/api/photos/connect")
async def connect(payload: dict | None = None):
    payload = payload or {}
    cid = str(payload.get("client_id") or "").strip()
    secret = str(payload.get("client_secret") or "").strip()
    if cid or secret:
        try:
            from config import credentials
            if cid:
                credentials.set_key("PHOTOS_GOOGLE_PHOTOS_CLIENT_ID", cid)
            if secret:
                credentials.set_key("PHOTOS_GOOGLE_PHOTOS_CLIENT_SECRET", secret)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    res = oauth.authorize_url(service.PROVIDER_ID)
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@router.get("/api/photos/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(_page(False, f"el proveedor devolvió un error: {error}"))
    res = oauth.exchange_code(code, state)
    # V2-700 — the CARD has to notice. See connectors/oauth_callback.announce().
    if res.get("ok"):
        from connectors import oauth_callback as _ocb
        _ocb.announce("fotos")
    return HTMLResponse(
        _page(bool(res.get("ok")), "" if res.get("ok") else str(res.get("error") or "no se pudo completar")),
        status_code=200 if res.get("ok") else 400)


@router.get("/api/photos/poll")
async def poll():
    return JSONResponse(service.poll_session())


@router.post("/api/photos/disconnect")
async def disconnect():
    _r = service.disconnect()
    # V2-700 — unlinking is a state change too: the card must stop saying «conectado».
    from connectors import oauth_callback as _ocb
    _ocb.announce("fotos")
    return JSONResponse(_r)


@router.get("/api/photos/thumb/{item_id}")
async def thumb(item_id: str):
    p = store.thumb_path(item_id)
    if not p.exists():
        return JSONResponse({"ok": False, "error": "sin miniatura"}, status_code=404)
    return FileResponse(str(p), media_type="image/jpeg")


def _page(ok: bool, detail: str) -> str:
    """The shared callback page (V2-700) — it is what tells the CARD the connection landed.

    Hand-rolled here until V2-700, in five near-identical copies that all had the same defect: they
    told the operator it had worked and told the widget nothing, so the card went on offering
    «Conectar». See `connectors/oauth_callback.py`."""
    from connectors import oauth_callback
    return oauth_callback.page(ok, detail, family='fotos', label='Google Photos',
                               done='Ya puedes elegir tus fotos desde la tarjeta de zaelar.')
