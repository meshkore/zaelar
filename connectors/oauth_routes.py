"""oauth_routes.py — the four HTTP doors every account connector opens, declared once.

Five connectors (`files`, `video`, `calendar`, `photos`, `contacts`) each hand-wrote the same four routes
under their own prefix, with the same error handling and the same «the card has to notice» step. The flow is
the one the product invariant demands — the operator configures everything from the interface, never by
editing files — and it is the same one Spotify (V2-041) and email (V2-055) use:

  1. `POST <prefix>/connect {provider, tier, client_id[, client_secret]}` — stores the app credentials in the
     credential store (only when the operator brings his own; a shared client needs none) and returns the
     consent URL. The frontend opens it in a window.
  2. `GET <prefix>/callback?code&state` — the provider redirects back HERE; the code is exchanged and a
     self-closing page is shown (`connectors/oauth_callback.py`).
  3. `GET <prefix>/status` — providers, whether each has an app registered, whether it is connected and which
     scope tier it was granted. REDACTED: a token never leaves this process.
  4. `POST <prefix>/disconnect {provider}` — forgets the tokens.

A connector declares a `Door` (its prefix, its widget family, its oauth module and provider table, its labels)
and calls `register`; its `server_api.py` keeps only what is genuinely its own (Photos' picker poll and
thumbnails, Calendar's first sync, the YouTube card refresh). Loopback, like the rest of the local API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from connectors import oauth_base as _b
from connectors import oauth_callback as _ocb


@dataclass(frozen=True)
class Door:
    """One account connector's HTTP face, as data."""
    prefix: str                         # "/api/cloudfiles" — checked free before choosing (see each server_api)
    family: str                         # the widget family the canvas refreshes by (`oauth_callback.FAMILY_WIDGET`)
    oauth: Any                          # the connector's oauth module: authorize_url, exchange_code, forget
    providers: Any                      # its provider table: get, public_list
    status: Callable[[], dict]          # the connector's own status body; the catalog is added to it here
    label: str                          # what the page names when no provider label is known…
    label_key: str = ""                 # …translated through this key when there is one
    done: str = ""                      # the success sentence, when the connector has a more useful one…
    done_key: str = ""                  # …and its key
    provider: str = ""                  # a single-provider door: fixed, and the request body names none
    default_provider: str = ""          # a multi-provider door: the provider when the body names none
    error_key: str = "oauth.err.provider"
    error_default: str = "the provider returned an error: {error}"
    error_status: int = 200
    on_connected: Callable[[str], None] | None = None   # what a SUCCESSFUL exchange also kicks off
    forget: Callable[[], dict] | None = None             # a single-provider door's disconnect, if not `oauth.forget`

    def page(self, ok: bool, detail: str, label: str = "") -> str:
        """The shared callback page (V2-700) — it is what tells the CARD the connection landed.

        Hand-rolled in each connector until V2-700, in five near-identical copies that all had the same defect:
        they told the operator it had worked and told the widget nothing, so the card went on offering
        «Conectar». See `connectors/oauth_callback.py`."""
        fallback = _ocb.text(self.label_key, self.label) if self.label_key else self.label
        done = _ocb.text(self.done_key, self.done) if self.done_key else ""
        return _ocb.page(ok, detail, family=self.family, label=label or fallback, done=done)


def _save_app(oauth_mod, pid: str, cid: str, secret: str) -> JSONResponse | None:
    """Store the OAuth app the operator brought, under the names `oauth_base` reads them back by."""
    if not (cid or secret):
        return None
    try:
        from config import credentials
        if cid:
            credentials.set_key(_b._key_name(oauth_mod, pid, "CLIENT_ID"), cid)
        if secret:
            credentials.set_key(_b._key_name(oauth_mod, pid, "CLIENT_SECRET"), secret)
    except Exception as e:  # noqa: BLE001 — reported to the form, never raised
        return JSONResponse({"ok": False, "error": f"credential_store:{e}"[:120]}, status_code=500)
    return None


def register(router: APIRouter, door: Door):
    """Mount status · connect · callback · disconnect for `door` on `router`. Returns the four endpoints, so a
    `server_api.py` can still name them (`callback`, `disconnect`) as its own."""

    @router.get(f"{door.prefix}/status")
    async def status():
        st = door.status()
        st["catalog"] = door.providers.public_list()
        return JSONResponse(st)

    @router.post(f"{door.prefix}/connect")
    async def connect(request: Request, payload: dict | None = None):
        """Save the OAuth app credentials (if sent) and start the PKCE consent. Returns {ok, url, tier}."""
        payload = payload or {}
        pid = door.provider or str(payload.get("provider") or door.default_provider).strip().lower()
        p = door.providers.get(pid)
        if not p:
            return JSONResponse({"ok": False, "error": f"proveedor desconocido: {pid or '(vacío)'}"},
                                status_code=400)
        refused = _save_app(door.oauth, p.id, str(payload.get("client_id") or "").strip(),
                            str(payload.get("client_secret") or "").strip())
        if refused:
            return refused
        # The origin the browser is actually on — the redirect is derived from it, never hardcoded (V2-603).
        res = door.oauth.authorize_url(p.id, str(payload.get("tier") or "").strip(),
                                       origin=_b.request_origin(request))
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @router.get(f"{door.prefix}/callback")
    async def callback(code: str = "", state: str = "", error: str = ""):
        if error:
            return HTMLResponse(door.page(False, _ocb.text(door.error_key, door.error_default, error=error)),
                                status_code=door.error_status)
        res = door.oauth.exchange_code(code, state)
        ok = bool(res.get("ok"))
        # V2-700 — the CARD has to notice. See connectors/oauth_callback.announce().
        if res.get("ok"):
            _ocb.announce(door.family)
            if door.on_connected:
                door.on_connected(str(res.get("provider") or ""))
        p = door.providers.get(res.get("provider") or "")
        detail = "" if ok else str(res.get("error") or _ocb.text("oauth.err.incomplete",
                                                                 "the connection could not be completed"))
        return HTMLResponse(door.page(ok, detail, p.label if p else ""), status_code=200 if ok else 400)

    if door.provider:
        @router.post(f"{door.prefix}/disconnect")
        async def disconnect():
            _r = door.forget() if door.forget else door.oauth.forget(door.provider)
            # V2-700 — unlinking is a state change too: the card must stop saying «conectado».
            _ocb.announce(door.family)
            return JSONResponse(_r)
    else:
        @router.post(f"{door.prefix}/disconnect")
        async def disconnect(payload: dict | None = None):
            pid = str((payload or {}).get("provider") or door.default_provider).strip().lower()
            if not door.providers.get(pid):
                return JSONResponse({"ok": False, "error": "proveedor desconocido"}, status_code=400)
            _r = door.oauth.forget(pid)
            # V2-700 — unlinking is a state change too: the card must stop saying «conectado».
            _ocb.announce(door.family)
            return JSONResponse(_r)

    return status, connect, callback, disconnect
