"""server_api.py — control plane for the calendar connectors (V2-679), at `/api/calendar/*`.

Prefix checked free before choosing it (`grep -rn '"/api/calendar' server/ connectors/` → nothing).

Same flow as `/api/video/*` and `/api/photos/*` (the product invariant: everything configured from the
interface, never by editing files):

  1. `POST /api/calendar/connect {provider, client_id[, client_secret][, tier]}` — stores the app credentials
     in the credential store and returns the consent URL. The frontend opens it in a window.
  2. `GET /api/calendar/callback?code&state` — the provider redirects back HERE; the code is exchanged, an
     initial sync + local-meeting migration runs, and a self-closing page is shown.
  3. `GET /api/calendar/status` — providers, whether each has an app registered and whether it is connected.
     REDACTED: a token never leaves this process.
  4. `POST /api/calendar/disconnect {provider}` — forgets the tokens (the local agenda store is untouched:
     what was already mirrored stays as plain local meetings, per the operator's "no perder nada" rule).

Loopback, like the rest of the local API.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from connectors.calendar import oauth, providers, service

router = APIRouter()


@router.get("/api/calendar/status")
async def status():
    st = service.status()
    st["catalog"] = providers.public_list()
    return JSONResponse(st)


@router.post("/api/calendar/connect")
async def connect(request: Request, payload: dict | None = None):
    payload = payload or {}
    pid = str(payload.get("provider") or "google").strip().lower()
    p = providers.get(pid)
    if not p:
        return JSONResponse({"ok": False, "error": f"proveedor desconocido: {pid or '(vacío)'}"}, status_code=400)
    cid = str(payload.get("client_id") or "").strip()
    secret = str(payload.get("client_secret") or "").strip()
    if cid or secret:
        try:
            from config import credentials
            if cid:
                credentials.set_key(f"CALENDAR_{p.id.upper()}_CLIENT_ID", cid)
            if secret:
                credentials.set_key(f"CALENDAR_{p.id.upper()}_CLIENT_SECRET", secret)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    res = oauth.authorize_url(p.id, str(payload.get("tier") or ""), origin=_origin(request))
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


def _origin(request: Request) -> str:
    try:
        o = (request.headers.get("origin") or "").strip()
        if o:
            return o
        host = (request.headers.get("host") or "").strip()
        if host:
            return f"{request.url.scheme}://{host}"
    except Exception:
        pass
    return ""


def _kick_agenda_sync() -> None:
    """First contact after consent: an immediate sync (so the operator sees their existing appointments right
    away, not after the next background tick) plus a one-time migration of pre-existing LOCAL meetings up to
    Google — the operator's explicit "no quiero divergencias" requirement. Both steps live in the WIDGET
    (`widgets/agenda/data.py::on_calendar_connected`), which already owns the dedup/twin-settlement rules this
    needs; this connector stays agenda-agnostic. Best-effort: a refresh failure must never turn a successful
    OAuth consent into a reported failure."""
    try:
        from widgets.agenda import data as adata
        adata.on_calendar_connected()
    except Exception:
        pass


@router.get("/api/calendar/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(_page(False, f"el proveedor devolvió un error: {error}"))
    res = oauth.exchange_code(code, state)
    # V2-700 — the CARD has to notice. See connectors/oauth_callback.announce().
    if res.get("ok"):
        from connectors import oauth_callback as _ocb
        _ocb.announce("agenda")
    ok = bool(res.get("ok"))
    if ok:
        _kick_agenda_sync()
    label = providers.get(res.get("provider") or "")
    return HTMLResponse(
        _page(ok, "" if ok else str(res.get("error") or "no se pudo completar la conexión"),
              label.label if label else "tu Google Calendar"),
        status_code=200 if ok else 400)


@router.post("/api/calendar/disconnect")
async def disconnect(payload: dict | None = None):
    pid = str((payload or {}).get("provider") or "google").strip().lower()
    if not providers.get(pid):
        return JSONResponse({"ok": False, "error": "proveedor desconocido"}, status_code=400)
    _r = oauth.forget(pid)
    # V2-700 — unlinking is a state change too: the card must stop saying «conectado».
    from connectors import oauth_callback as _ocb
    _ocb.announce("agenda")
    return JSONResponse(_r)


def _page(ok: bool, detail: str, label: str = 'tu Google Calendar') -> str:
    """The shared callback page (V2-700) — it is what tells the CARD the connection landed.

    Hand-rolled here until V2-700, in five near-identical copies that all had the same defect: they
    told the operator it had worked and told the widget nothing, so the card went on offering
    «Conectar». See `connectors/oauth_callback.py`."""
    from connectors import oauth_callback
    return oauth_callback.page(ok, detail, family='agenda', label=label,
                               done='Tu agenda ya se está sincronizando con Google Calendar.')
