#
# oauth.py — OAuth2 (authorization-code + PKCE) for email, provider MODEL-AGNOSTIC (V2-055). Gmail and
# Outlook/Microsoft share the SAME flow (endpoints/scopes come from the `providers.py` registry), and transport
# remains IMAP/SMTP with SASL XOAUTH2 (the access token replaces the password; see `mailbox.xoauth2_sasl`).
#
# Pattern copied from `connectors/spotify/auth.py` (V2-041): PKCE S256 (without exposing a secret in installed apps),
# callback served by zaelar's OWN server (`server/email_api.py` → /api/email/callback), tokens in the credential
# store (`.meshkore/credentials/email_oauth.json`, chmod 600, gitignored — NEVER in the repo or frontend).
# UI-managed config: app `client_id`/`secret` (Google Cloud / Microsoft Entra) are set by the operator ONCE;
# DORMANT until then (like Spotify).
#
# All functions are SYNCHRONOUS and FAIL-SAFE (return {ok:False,...} or None; never raise to the caller).
#
from __future__ import annotations

import logging
import os
import time
import urllib.parse
from pathlib import Path

from connectors.email import providers as _pv
from connectors.oauth_pkce import make_pkce, make_state
from connectors.secure_json_store import SecureJsonStore

logger = logging.getLogger("zaelar.email.oauth")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _ROOT / ".meshkore" / "credentials" / "email_oauth.json"
_REFRESH_SKEW = 120                      # refresca 2 min antes de caducar
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/email/callback"


# ── App credentials (credential store; dormant if empty) ────────────────────────────────────────────────────────
def _cred(name: str) -> str:
    try:
        from config import credentials as store
        v = (store.get(name) or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv(name) or "").strip()


def client_id(provider_id: str) -> str:
    return _cred(f"EMAIL_{provider_id.upper()}_CLIENT_ID")


def client_secret(provider_id: str) -> str:
    return _cred(f"EMAIL_{provider_id.upper()}_CLIENT_SECRET")


def configured(provider_id: str) -> bool:
    """Is there an OAuth app registered for this provider? (if not, the widget offers the app-password path)."""
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return False
    return bool(client_id(provider_id))


def redirect_uri() -> str:
    return os.getenv("EMAIL_OAUTH_REDIRECT") or _DEFAULT_REDIRECT


# ── Token + pending store (per provider:account) ───────────────────────────────────────────────────────────────
# A fresh SecureJsonStore(STORE) per call, not a module-level singleton: tests monkeypatch `oauth.STORE` to a
# tmp path, which a cached instance bound to the ORIGINAL path at import time would silently ignore.
def _load() -> dict:
    return SecureJsonStore(STORE).load()


def _save(data: dict) -> None:
    try:
        SecureJsonStore(STORE).save(data)
    except Exception as e:
        logger.warning(f"email oauth store no guardado: {e}")


def _acct_key(provider_id: str, address: str) -> str:
    return f"{provider_id}:{(address or '').strip().lower()}"


def tokens_present(provider_id: str, address: str) -> bool:
    return bool((_load().get("accounts", {}) or {}).get(_acct_key(provider_id, address), {}).get("refresh_token"))


def forget(provider_id: str, address: str) -> None:
    data = _load()
    (data.get("accounts", {}) or {}).pop(_acct_key(provider_id, address), None)
    _save(data)


# ── authorization-code flow ────────────────────────────────────────────────────────────────────────────────────
def authorize_url(provider_id: str, address: str = "") -> dict:
    """Return {ok, url} — the consent URL to send the user to. Stashes the PKCE verifier + provider/account under a
    random `state` (for the callback)."""
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return {"ok": False, "error": f"proveedor sin OAuth: {provider_id}"}
    cid = client_id(provider_id)
    if not cid:
        return {"ok": False, "error": f"sin app OAuth registrada para {p.label} (falta EMAIL_{provider_id.upper()}_CLIENT_ID)"}
    verifier, challenge = make_pkce()
    state = make_state()
    data = _load()
    data.setdefault("pending", {})[state] = {"provider": provider_id, "address": address,
                                             "verifier": verifier, "ts": int(time.time())}
    _save(data)
    params = {
        "client_id": cid, "response_type": "code", "redirect_uri": redirect_uri(),
        "scope": " ".join(p.oauth.scopes), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",       # Google: forces refresh_token; Microsoft ignores it
    }
    if address:
        params["login_hint"] = address
    return {"ok": True, "url": p.oauth.authorize_url + "?" + urllib.parse.urlencode(params)}


def exchange_code(code: str, state: str) -> dict:
    """Callback: exchange `code` for tokens using the pending `state`. Saves access/refresh/expiry per account.
    Returns {ok, provider, address}."""
    import httpx
    data = _load()
    pend = (data.get("pending", {}) or {}).pop(state, None)
    _save(data)
    if not pend:
        return {"ok": False, "error": "state desconocido o caducado"}
    provider_id = pend["provider"]
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return {"ok": False, "error": "proveedor inválido"}
    body = {
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": client_id(provider_id), "code_verifier": pend["verifier"],
    }
    sec = client_secret(provider_id)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(p.oauth.token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:
        return {"ok": False, "error": f"intercambio falló: {e}"}
    if "access_token" not in tok:
        return {"ok": False, "error": f"sin access_token: {tok.get('error_description') or tok.get('error') or tok}"}
    address = pend.get("address") or ""
    _store_tokens(provider_id, address, tok)
    return {"ok": True, "provider": provider_id, "address": address}


def _store_tokens(provider_id: str, address: str, tok: dict) -> None:
    data = _load()
    accts = data.setdefault("accounts", {})
    cur = accts.get(_acct_key(provider_id, address), {})
    entry = {
        "access_token": tok.get("access_token", ""),
        # refresh_token does not always return on refresh → preserve the previous one
        "refresh_token": tok.get("refresh_token") or cur.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)),
    }
    accts[_acct_key(provider_id, address)] = entry
    _save(data)


def access_token(provider_id: str, address: str) -> str | None:
    """Return a VALID access token (refreshing if expired) or None. Used by the connector for XOAUTH2."""
    import httpx
    acct = (_load().get("accounts", {}) or {}).get(_acct_key(provider_id, address))
    if not acct:
        return None
    if acct.get("access_token") and acct.get("expires_at", 0) - _REFRESH_SKEW > time.time():
        return acct["access_token"]
    rt = acct.get("refresh_token")
    p = _pv.get(provider_id)
    if not rt or not p or not p.oauth:
        return acct.get("access_token") or None
    body = {"grant_type": "refresh_token", "refresh_token": rt, "client_id": client_id(provider_id),
            "scope": " ".join(p.oauth.scopes)}
    sec = client_secret(provider_id)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(p.oauth.token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:
        logger.warning(f"email oauth refresh falló ({provider_id}): {e}")
        return acct.get("access_token") or None
    if "access_token" in tok:
        _store_tokens(provider_id, address, tok)
        return tok["access_token"]
    return acct.get("access_token") or None
