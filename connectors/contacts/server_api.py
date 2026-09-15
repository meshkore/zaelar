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
    return HTMLResponse(
        _page(bool(res.get("ok")), "" if res.get("ok") else str(res.get("error") or "no se pudo completar")),
        status_code=200 if res.get("ok") else 400)


@router.post("/api/contacts/disconnect")
async def disconnect():
    return JSONResponse(oauth.forget("google-contacts"))


def _page(ok: bool, detail: str) -> str:
    title = "Google Contacts conectado" if ok else "No se pudo conectar"
    icon = "✅" if ok else "⚠️"
    body = ("Vuelve a la tarjeta de Contactos y pulsa «Importar de Google». Puedes cerrar esta pestaña."
            if ok else f"Detalle: {detail}. Cierra esta pestaña e inténtalo de nuevo desde el widget.")
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e6e6e6;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
        ".c{max-width:28rem;text-align:center;padding:2rem}h1{font-size:1.3rem;margin:.5rem 0}"
        "p{color:#9aa0aa;line-height:1.5}</style></head><body><div class='c'>"
        f"<div style='font-size:3rem'>{icon}</div><h1>{title}</h1><p>{body}</p>"
        "<script>setTimeout(function(){try{window.close()}catch(e){}},4000)</script>"
        "</div></body></html>"
    )
