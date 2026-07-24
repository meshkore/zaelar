"""server/spotify_api.py — plano de control OAuth + estado del conector Spotify (V2-041).

Config gestionada por la UI (invariante de producto): el operador conecta Spotify DESDE la interfaz, nunca editando
ficheros. Flujo:
  1. `POST /api/spotify/connect {client_id}` → guarda el client_id en el credential store y devuelve la URL de
     autorización de Spotify (PKCE). El frontend la abre en una ventana.
  2. Spotify redirige a `GET /api/spotify/callback?code&state` (este mismo servidor) → canjea el code por tokens.
  3. `GET /api/spotify/status` → presencia de client_id + si hay sesión (REDACTADO, nunca el token).
  4. `POST /api/spotify/disconnect` → borra los tokens.

Loopback (app de escritorio local single-user), como el resto de la API de zaelar. El seam genérico de música
(`GET /api/music/state`) queda para el widget de música (pieza SEPARADA) y el diagnóstico.
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
    """Guarda el client_id (si viene) y arranca el login PKCE. Devuelve la URL de autorización a abrir."""
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
    """Vuelta de Spotify tras el consentimiento. Canjea el code y muestra una página de cierre."""
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
    """Estado del seam de música (todos los proveedores conocidos + los conectados). Para el widget futuro."""
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
