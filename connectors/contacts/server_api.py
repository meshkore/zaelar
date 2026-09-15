"""server_api.py — control plane for the contacts connector (V2-699), at `/api/contacts/*`.

Checked free first (`grep -rn '"/api/contacts' server/ connectors/ widgets/`) — nothing else in this repo
answers that prefix.

  1. `POST /api/contacts/connect {client_id[, client_secret][, tier]}` — stores the OAuth app credentials
     (only when the operator brings his own; the shared Google client needs none) and starts consent.
     Returns {ok, url}; ⚙ → Conectores opens it in a window.
  2. `GET /api/contacts/callback?code&state` — Google redirects back HERE after consent.
  3. `GET /api/contacts/status` — app registered? connected? which tier?
  4. `POST /api/contacts/disconnect` — forgets the tokens.

The IMPORT itself is deliberately NOT here. It is the widget's own declared action
(`widgets/contactos` → `import_google`), because the merge belongs to whoever owns the store, and because
an action is the thing the voice can reach — an HTTP endpoint is not.

Loopback, like the rest of the local API.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from connectors.contacts import oauth, providers

router = APIRouter()


@router.get("/api/contacts/status")
async def status():
    return JSONResponse({"ok": True, "providers": oauth.status(), "catalog": providers.public_list()})


@router.post("/api/contacts/connect")
async def connect(request: Request, payload: dict | None = None):
    payload = payload or {}
    cid = str(payload.get("client_id") or "").strip()
    secret = str(payload.get("client_secret") or "").strip()
    tier = str(payload.get("tier") or "").strip()
    if cid or secret:
        try:
            from config import credentials
            if cid:
                credentials.set_key("CONTACTS_GOOGLE_CONTACTS_CLIENT_ID", cid)
            if secret:
                credentials.set_key("CONTACTS_GOOGLE_CONTACTS_CLIENT_SECRET", secret)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    # The origin the browser is actually on — the redirect is derived from it, never hardcoded (V2-603).
    origin = str(request.headers.get("origin") or "").strip()
    res = oauth.authorize_url("google-contacts", tier, origin)
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@router.get("/api/contacts/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(_page(False, f"Google devolvió un error: {error}"), status_code=400)
    res = oauth.exchange_code(code, state)
    # V2-700 — the CARD has to notice. See connectors/oauth_callback.announce().
    if res.get("ok"):
        from connectors import oauth_callback as _ocb
        _ocb.announce("contactos")
    return HTMLResponse(
        _page(bool(res.get("ok")), "" if res.get("ok") else str(res.get("error") or "no se pudo completar")),
        status_code=200 if res.get("ok") else 400)


@router.post("/api/contacts/disconnect")
async def disconnect():
    _r = oauth.forget("google-contacts")
    # V2-700 — unlinking is a state change too: the card must stop saying «conectado».
    from connectors import oauth_callback as _ocb
    _ocb.announce("contactos")
    return JSONResponse(_r)


def _page(ok: bool, detail: str) -> str:
    """The shared callback page (V2-700) — it is what tells the CARD the connection landed.

    Hand-rolled here until V2-700, in five near-identical copies that all had the same defect: they
    told the operator it had worked and told the widget nothing, so the card went on offering
    «Conectar». See `connectors/oauth_callback.py`."""
    from connectors import oauth_callback
    return oauth_callback.page(ok, detail, family='contactos', label='Google Contacts',
                               done='Vuelve a la tarjeta de Contactos y pulsa «Sincronizar contactos».')
