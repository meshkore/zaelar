"""oauth.py — OAuth2 (authorization-code + PKCE) for the contacts connector (V2-699).

Same shape as `connectors/photos/oauth.py` (V2-564) and `connectors/files/oauth.py` (V2-557): PKCE S256 so
an installed app never ships a secret, the callback served by zaelar's OWN server, tokens in the credential
store (`.meshkore/credentials/contacts_oauth.json`, chmod 600, gitignored — NEVER in the repo or the
frontend).

UI-managed config (product invariant): the operator registers the OAuth app ONCE from the Connectors tab and
the connector stays DORMANT until then — no credentials in `.env`, and nothing here raises to its caller.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.parse
from pathlib import Path

from connectors.contacts import providers as _pv
from connectors.oauth_pkce import make_pkce, make_state
from connectors.secure_json_store import SecureJsonStore

logger = logging.getLogger("zaelar.contacts.oauth")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _ROOT / ".meshkore" / "credentials" / "contacts_oauth.json"
_REFRESH_SKEW = 120
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/contacts/callback"
_PENDING_TTL = 900


def _cred(name: str) -> str:
    try:
        from config import credentials as store
        v = (store.get(name) or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv(name) or "").strip()


# V2-685 — the ONE Google app. The connector's OWN name still wins: a self-hoster who wants a separate
# OAuth client for their address book keeps it.
_GOOGLE_PROVIDERS = {"google-contacts"}


def _shipped_google(provider_id: str, *, secret: bool) -> str:
    if provider_id not in _GOOGLE_PROVIDERS:
        return ""
    try:
        from connectors.google import app as _google
        return _google.client_secret() if secret else _google.client_id()
    except Exception:  # noqa: BLE001 — a missing shared app leaves the connector exactly as dormant as before
        return ""


def client_id(provider_id: str) -> str:
    return _cred(f"CONTACTS_{provider_id.upper().replace('-', '_')}_CLIENT_ID") \
        or _shipped_google(provider_id, secret=False)


def client_secret(provider_id: str) -> str:
    return _cred(f"CONTACTS_{provider_id.upper().replace('-', '_')}_CLIENT_SECRET") \
        or _shipped_google(provider_id, secret=True)


def configured(provider_id: str) -> bool:
    return bool(_pv.get(provider_id) and client_id(provider_id))


def redirect_uri(origin: str = "") -> str:
    """The return address Google is asked for — DERIVED from where the browser is, then normalized.

    ⚠️ Not a constant. `connectors/google/app.py::normalize_origin` collapses this engine's two local
    listeners onto loopback, because Google exempts `127.0.0.1` from domain ownership and `local.zaelar.com`
    is a domain nobody self-hosting can verify. Deriving the redirect from whichever listener the operator
    happened to open is what V2-687 paid for.
    """
    env = (os.getenv("CONTACTS_OAUTH_REDIRECT") or "").strip()
    if env:
        return env
    try:
        from connectors.google import app as _google
        base = _google.normalize_origin(origin) or _google.loopback_origin()
        return base.rstrip("/") + "/api/contacts/callback"
    except Exception:
        return _DEFAULT_REDIRECT


def _load() -> dict:
    return SecureJsonStore(STORE).load()


def _save(data: dict) -> None:
    try:
        SecureJsonStore(STORE).save(data)
    except Exception as e:
        logger.warning(f"contacts oauth store not saved: {e}")


def _accounts(data: dict | None = None) -> dict:
    return (data if data is not None else _load()).get("accounts", {}) or {}


def account(provider_id: str) -> dict:
    return _accounts().get((provider_id or "").strip().lower(), {}) or {}


def tokens_present(provider_id: str) -> bool:
    return bool(account(provider_id).get("refresh_token"))


def forget(provider_id: str) -> dict:
    data = _load()
    (data.get("accounts", {}) or {}).pop((provider_id or "").strip().lower(), None)
    _save(data)
    return {"ok": True, "provider": provider_id}


def authorize_url(provider_id: str = "google-contacts", tier_id: str = "", origin: str = "") -> dict:
    p = _pv.get(provider_id)
    if not p:
        return {"ok": False, "error": f"proveedor desconocido: {provider_id}"}
    cid = client_id(p.id)
    if not cid:
        return {"ok": False, "error": f"sin app OAuth registrada para {p.label} (falta el client_id)"}
    tier = p.tier(tier_id)
    verifier, challenge = make_pkce()
    state = make_state()
    data = _load()
    pend = data.setdefault("pending", {})
    now = int(time.time())
    for k, v in list(pend.items()):
        if now - int(v.get("ts") or 0) > _PENDING_TTL:
            pend.pop(k, None)
    ruri = redirect_uri(origin)
    # The redirect is stored WITH the pending state: the token exchange must present the exact same URI
    # Google saw, and re-deriving it from a different request would fail at the last step with
    # `redirect_uri_mismatch` — the one error that looks like a credential problem and is not.
    pend[state] = {"provider": p.id, "tier": tier.id, "verifier": verifier, "ts": now, "redirect": ruri}
    _save(data)
    params = {
        "client_id": cid, "response_type": "code", "redirect_uri": ruri,
        "scope": " ".join(tier.scopes), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        **(p.extra_auth_params or {}),
    }
    return {"ok": True, "url": p.authorize_url + "?" + urllib.parse.urlencode(params), "tier": tier.id}


def exchange_code(code: str, state: str) -> dict:
    import httpx
    data = _load()
    pend = (data.get("pending", {}) or {}).pop(state, None)
    _save(data)
    if not pend:
        return {"ok": False, "error": "state desconocido o caducado"}
    p = _pv.get(pend.get("provider") or "")
    if not p:
        return {"ok": False, "error": "proveedor inválido"}
    body = {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": pend.get("redirect") or redirect_uri(),
        "client_id": client_id(p.id), "code_verifier": pend["verifier"],
    }
    sec = client_secret(p.id)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(p.token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:
        return {"ok": False, "error": f"intercambio falló: {e}"}
    if "access_token" not in tok:
        return {"ok": False, "error": f"sin access_token: "
                                      f"{tok.get('error_description') or tok.get('error') or tok}"}
    _store_tokens(p.id, pend.get("tier") or p.default_tier, tok)
    return {"ok": True, "provider": p.id, "tier": pend.get("tier") or p.default_tier}


def _store_tokens(provider_id: str, tier_id: str, tok: dict) -> None:
    data = _load()
    accts = data.setdefault("accounts", {})
    cur = accts.get(provider_id, {}) or {}
    accts[provider_id] = {
        "access_token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token") or cur.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tok.get("expires_in", 3600) or 3600),
        "tier": tier_id or cur.get("tier") or "",
    }
    _save(data)


def access_token(provider_id: str) -> str | None:
    import httpx
    pid = (provider_id or "").strip().lower()
    acct = account(pid)
    if not acct:
        return None
    if acct.get("access_token") and int(acct.get("expires_at", 0)) - _REFRESH_SKEW > time.time():
        return acct["access_token"]
    rt = acct.get("refresh_token")
    p = _pv.get(pid)
    if not rt or not p:
        return acct.get("access_token") or None
    tier = p.tier(acct.get("tier") or "")
    body = {"grant_type": "refresh_token", "refresh_token": rt, "client_id": client_id(pid),
            "scope": " ".join(tier.scopes)}
    sec = client_secret(pid)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(p.token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:
        logger.warning(f"contacts oauth refresh failed ({pid}): {e}")
        return acct.get("access_token") or None
    if "access_token" in tok:
        _store_tokens(pid, acct.get("tier") or "", tok)
        return tok["access_token"]
    return acct.get("access_token") or None


def status() -> list[dict]:
    out = []
    for p in _pv.PROVIDERS.values():
        tier = p.tier(account(p.id).get("tier") or "")
        out.append({
            "id": p.id, "label": p.label, "app_configured": configured(p.id),
            "connected": tokens_present(p.id), "tier": tier.id, "tier_label": tier.label, "note": p.note,
        })
    return out
