"""server_api.py — control plane for the cloud-file connectors (V2-557), at `/api/cloudfiles/*`.

Deliberately NOT `/api/files/*`: that prefix is already owned by `server/memory_routes.py` (paste/drop uploads
into episodic memory, V2-003). Two routers answering one prefix is a collision that FastAPI resolves by
registration order — silently, and in favour of whichever was mounted first.

The flow is the one the product invariant demands (the operator configures everything from the interface,
never by editing files), and it is the same one Spotify (V2-041) and email (V2-055) already use:

  1. `POST /api/cloudfiles/connect {provider, tier, client_id[, client_secret]}` — stores the app credentials in
     the credential store and returns the consent URL. The frontend opens it in a window.
  2. `GET /api/cloudfiles/callback?code&state` — the provider redirects back HERE; the code is exchanged and a
     closing page is shown.
  3. `GET /api/cloudfiles/status` — providers, whether each has an app registered, whether it is connected and
     WHICH scope tier it was granted. REDACTED: a token never leaves this process.
  4. `POST /api/cloudfiles/disconnect {provider}` — forgets the tokens.

Loopback, like the rest of the local API.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from connectors.files import oauth, providers, service

router = APIRouter()


@router.get("/api/cloudfiles/status")
async def status():
    st = service.status()
    st["catalog"] = providers.public_list()
    return JSONResponse(st)


@router.post("/api/cloudfiles/connect")
async def connect(payload: dict | None = None):
    """Save the OAuth app credentials (if sent) and start the PKCE consent. Returns {ok, url, tier}."""
    payload = payload or {}
    pid = str(payload.get("provider") or "").strip().lower()
    p = providers.get(pid)
    if not p:
        return JSONResponse({"ok": False, "error": f"proveedor desconocido: {pid or '(vacío)'}"}, status_code=400)
    cid = str(payload.get("client_id") or "").strip()
    secret = str(payload.get("client_secret") or "").strip()
    if cid or secret:
        try:
            from config import credentials
            if cid:
                credentials.set_key(f"FILES_{p.id.upper()}_CLIENT_ID", cid)
            if secret:
                credentials.set_key(f"FILES_{p.id.upper()}_CLIENT_SECRET", secret)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    res = oauth.authorize_url(p.id, str(payload.get("tier") or ""))
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@router.get("/api/cloudfiles/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(_page(False, f"el proveedor devolvió un error: {error}"))
    res = oauth.exchange_code(code, state)
    ok = bool(res.get("ok"))
    label = (providers.get(res.get("provider") or "") or None)
    return HTMLResponse(
        _page(ok, "" if ok else str(res.get("error") or "no se pudo completar la conexión"),
              label.label if label else "tus archivos"),
        status_code=200 if ok else 400)


@router.post("/api/cloudfiles/disconnect")
async def disconnect(payload: dict | None = None):
    pid = str((payload or {}).get("provider") or "").strip().lower()
    if not providers.get(pid):
        return JSONResponse({"ok": False, "error": "proveedor desconocido"}, status_code=400)
    return JSONResponse(oauth.forget(pid))


def _page(ok: bool, detail: str, label: str = "tus archivos") -> str:
    title = f"{label} conectado" if ok else "No se pudo conectar"
    icon = "✅" if ok else "⚠️"
    body = ("Ya puedes pedirle a zaelar que abra o busque en tus archivos. Puedes cerrar esta pestaña."
            if ok else f"Detalle: {detail}. Cierra esta pestaña e inténtalo de nuevo desde la configuración.")
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
