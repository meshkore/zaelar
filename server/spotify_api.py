"""server/spotify_api.py — OAuth control plane + Spotify connector state (V2-041).

UI-managed config (product invariant): the operator connects Spotify FROM the interface, never by editing files.
Flow:
  1. `POST /api/spotify/connect {client_id}` → saves the client_id in the credential store and returns the Spotify
     authorization URL (PKCE). The frontend opens it in a window.
  2. Spotify redirects to `GET /api/spotify/callback?code&state` (this same server) → exchanges the code for tokens.
  3. `GET /api/spotify/status` → client_id presence + whether there is a session (REDACTED, never the token).
  4. `POST /api/spotify/disconnect` → deletes the tokens.

Loopback (single-user local desktop app), like the rest of the zaelar API. The generic music seam
(`GET /api/music/state`) remains for the music widget (SEPARATE piece) and diagnostics.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from connectors.spotify import auth

router = APIRouter()


@router.get("/api/spotify/status")
async def status():
    return JSONResponse(auth.status())


@router.post("/api/spotify/connect")
async def connect(payload: dict | None = None):
    """Save the client_id (if provided) and start PKCE login. Returns the authorization URL to open."""
    payload = payload or {}
    cid = (payload.get("client_id") or "").strip()
    if cid:
        try:
            from config import credentials
            credentials.set_key("SPOTIFY_CLIENT_ID", cid)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    res = auth.begin_login()
    if not res.get("ok"):
        code = 400 if res.get("error") == "no_client_id" else 500
        return JSONResponse(res, status_code=code)
    return JSONResponse(res)


@router.get("/api/spotify/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    """Return from Spotify after consent. Exchanges the code and shows a closing page."""
    if error:
        return HTMLResponse(_page(False, f"Spotify devolvió un error: {error}"))
    res = auth.complete_login(code, state)
    ok = bool(res.get("ok"))
    return HTMLResponse(_page(ok, "" if ok else res.get("error", "no se pudo completar la conexión")),
                        status_code=200 if ok else 400)


@router.post("/api/spotify/disconnect")
async def disconnect():
    return JSONResponse(auth.disconnect())


@router.get("/api/music/state")
async def music_state():
    """Music seam state (all known providers + connected ones). For the future widget."""
    from connectors import music
    return JSONResponse(music.status())


def _page(ok: bool, detail: str) -> str:
    title = "Spotify conectado" if ok else "No se pudo conectar"
    icon = "✅" if ok else "⚠️"
    body = ("Ya puedes pedirle música a zaelar por voz. Puedes cerrar esta pestaña."
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
