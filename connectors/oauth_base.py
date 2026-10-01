"""One OAuth2 flow (authorization code + PKCE S256) for every account connector (V2-778 F1-13, 2026-10-01).

Six connectors — calendar, video, contacts, files, photos, email — each carried their own copy of the same
~230 lines, and the copies had drifted: three of them still sent the provider back to a hardcoded loopback
address (the V2-603 failure, fixed in the other three), one never expired its pending states, one crashed on
a token response without `expires_in`. This is the one place the flow lives now.

How a connector uses it: its `oauth.py` keeps its own CONFIGURATION as module attributes — where it stores
tokens (`STORE`), the prefix of its credential names (`ENV_PREFIX`), the path it is called back on
(`CALLBACK_PATH`), which of its providers ride Zaelar's shared Google app (`_GOOGLE_PROVIDERS`), its provider
table (`_pv`) — and its public functions are thin calls into this module, passing itself. Everything here is
read THROUGH that module at call time (`m.client_id(...)`, `m.STORE`, `m._load()`), so a connector can still
override one piece by defining it, and a test that patches `oauth.client_id` still governs the whole flow.

Each connector stays independent: it owns its store file, its callback route and its credential names, so
nothing here is a shared token store and no connector can read another's accounts.

Fail-safe like the copies were: nothing raises to the caller; a missing app leaves a connector dormant.
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse

from connectors.oauth_pkce import make_pkce, make_state
from connectors.secure_json_store import SecureJsonStore

#: scheme://host[:port] and nothing else — no path, no query, no control characters. The origin arrives from a
#: request header, so it is untrusted input that ends up inside a URL handed to the provider.
_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(?::\d{1,5})?$")
PENDING_TTL = 900          # a consent started and never finished stops being acceptable after 15 minutes
REFRESH_SKEW = 120         # refresh two minutes before the access token expires


# ── credentials and the app ───────────────────────────────────────────────────────────────────────────────

def cred(name: str) -> str:
    """A credential from the store the UI writes, else the environment (power-user fallback), else ""."""
    try:
        from config import credentials as store
        v = (store.get(name) or "").strip()
        if v:
            return v
    except Exception:  # noqa: BLE001 — no credential store just means «not configured»
        pass
    return (os.getenv(name) or "").strip()


def _key_name(m, provider_id: str, what: str) -> str:
    return f"{m.ENV_PREFIX}_{provider_id.upper().replace('-', '_')}_{what}"


def shipped_google(m, provider_id: str, *, secret: bool = False) -> str:
    """Zaelar's shared Google client (`connectors/google/app.py`), or "" when this provider is not a Google one
    or none is installed. Resolved on each call: the operator can drop the console's JSON in while the engine
    runs, and a value frozen at import would leave him restarting to be believed (V2-685)."""
    if provider_id not in getattr(m, "_GOOGLE_PROVIDERS", ()):
        return ""
    try:
        from connectors.google import app as _google
        return _google.client_secret() if secret else _google.client_id()
    except Exception:  # noqa: BLE001 — no shared app just leaves the connector dormant
        return ""


def _builtin(m, provider_id: str) -> str:
    p = m._pv.get(provider_id)
    return (getattr(p, "builtin_client_id", "") or "").strip() if p else ""


def client_id(m, provider_id: str) -> str:
    """The OAuth client this install uses: the operator's OWN always wins; otherwise one the provider table
    ships, otherwise Zaelar's shared Google app. "" when none exists — the connector then stays dormant."""
    return (m._cred(_key_name(m, provider_id, "CLIENT_ID")) or _builtin(m, provider_id)
            or m._shipped_google(provider_id, secret=False))


def uses_builtin_app(m, provider_id: str) -> bool:
    """True when this install rides a shipped client rather than one the operator registered — what decides
    whether the wizard is one consent step or the whole bring-your-own-app road."""
    return not m._cred(_key_name(m, provider_id, "CLIENT_ID")) and bool(
        _builtin(m, provider_id) or m._shipped_google(provider_id, secret=False))


def client_secret(m, provider_id: str) -> str:
    return m._cred(_key_name(m, provider_id, "CLIENT_SECRET")) or m._shipped_google(provider_id, secret=True)


# ── the return address ────────────────────────────────────────────────────────────────────────────────────

def redirect_uri(m, origin: str = "") -> str:
    """Where the provider sends the operator back — DERIVED from the origin they are actually on (V2-603).

    An explicit `<PREFIX>_OAUTH_REDIRECT` wins (a deployment that knows its public address). Otherwise the
    origin, with this engine's two local listeners collapsed onto loopback (`google/app.normalize_origin`:
    Google exempts `127.0.0.1` from domain ownership, V2-687), accepted only if it LOOKS like an origin. With
    no usable origin, the loopback listener — which is what a hardcoded `127.0.0.1:43917` meant, minus the
    port it could not see."""
    env = (os.getenv(f"{m.ENV_PREFIX}_OAUTH_REDIRECT") or "").strip()
    if env:
        return env
    try:
        from connectors.google import app as _google
        o = _google.normalize_origin((origin or "").strip().rstrip("/"))
        if not (o and _ORIGIN_RE.match(o)):
            o = _google.loopback_origin()
        return o.rstrip("/") + m.CALLBACK_PATH
    except Exception:  # noqa: BLE001 — without the shared module, the address it always had
        return m._DEFAULT_REDIRECT


def request_origin(request) -> str:
    """The origin the browser is on: its `Origin` header, else scheme + `Host`. Untrusted — `redirect_uri`
    validates it before it reaches a URL."""
    try:
        o = (request.headers.get("origin") or "").strip()
        if o:
            return o
        host = (request.headers.get("host") or "").strip()
        if host:
            return f"{request.url.scheme}://{host}"
    except Exception:  # noqa: BLE001 — no readable request means no origin, and the loopback default
        pass
    return ""


# ── the token store ───────────────────────────────────────────────────────────────────────────────────────

def load(m) -> dict:
    return SecureJsonStore(m.STORE).load()


def save(m, data: dict) -> None:
    try:
        SecureJsonStore(m.STORE).save(data)
    except Exception as e:  # noqa: BLE001 — a store that cannot be written is logged, never raised
        m.logger.warning(f"{m.ENV_PREFIX.lower()} oauth store not saved: {e}")


def account(m, key: str) -> dict:
    return (m._load().get("accounts", {}) or {}).get(key, {}) or {}


def forget(m, key: str) -> None:
    data = m._load()
    (data.get("accounts", {}) or {}).pop(key, None)
    m._save(data)


def store_tokens(m, key: str, tier_id: str, tok: dict) -> None:
    data = m._load()
    accts = data.setdefault("accounts", {})
    cur = accts.get(key, {}) or {}
    accts[key] = {
        "access_token": tok.get("access_token", ""),
        # A refresh response does not always return the refresh_token → keep the previous one, or the second
        # refresh of the day would silently disconnect the operator (V2-557's measured trap).
        "refresh_token": tok.get("refresh_token") or cur.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tok.get("expires_in", 3600) or 3600),
        "tier": tier_id or cur.get("tier") or "",
    }
    m._save(data)


# ── the flow ──────────────────────────────────────────────────────────────────────────────────────────────

def spec(p, tier_id: str = "") -> tuple[str, str, list, dict]:
    """(authorize_url, token_url, scopes, extra_params) of a TIERED provider — the shape five of the six
    provider tables share. A connector whose providers look different defines its own `_auth_spec`."""
    return p.authorize_url, p.token_url, list(p.tier(tier_id).scopes), dict(p.extra_auth_params or {})


def _capable(m, p) -> bool:
    """A provider this connector can run OAuth against — every one, unless the connector says otherwise
    (`_oauth_capable`: email lists IMAP-only providers beside the OAuth ones)."""
    return bool(p) and (m._oauth_capable(p) if hasattr(m, "_oauth_capable") else True)


def _spec(m, p, tier_id: str):
    return m._auth_spec(p, tier_id) if hasattr(m, "_auth_spec") else spec(p, tier_id)


def authorize_url(m, provider_id: str, tier_id: str = "", origin: str = "", *,
                  pending: dict | None = None, params: dict | None = None) -> dict:
    """{ok, url, tier} — the consent URL. Stashes the PKCE verifier, the provider, the chosen tier and the
    return address under a random `state`: the callback carries nothing but `code` and `state`, and the
    exchange must present the SAME redirect the consent was asked with."""
    p = m._pv.get(provider_id)
    if not _capable(m, p):
        return {"ok": False, "error": f"proveedor desconocido o sin OAuth: {provider_id}"}
    cid = m.client_id(p.id)
    if not cid:
        return {"ok": False, "error": f"sin app OAuth registrada para {p.label} "
                                      f"(falta el client_id: {_key_name(m, p.id, 'CLIENT_ID')})"}
    auth_url, _token_url, scopes, extra = _spec(m, p, tier_id)
    tier = p.tier(tier_id).id if hasattr(p, "tier") else ""
    verifier, challenge = make_pkce()
    state = make_state()
    data = m._load()
    pend = data.setdefault("pending", {})
    now = int(time.time())
    for k, v in list(pend.items()):
        if now - int((v or {}).get("ts") or 0) > getattr(m, "_PENDING_TTL", PENDING_TTL):
            pend.pop(k, None)
    ruri = m.redirect_uri(origin)
    pend[state] = {"provider": p.id, "tier": tier, "verifier": verifier, "ts": now, "redirect": ruri,
                   **(pending or {})}
    m._save(data)
    q = {"client_id": cid, "response_type": "code", "redirect_uri": ruri, "scope": " ".join(scopes),
         "state": state, "code_challenge": challenge, "code_challenge_method": "S256", **extra, **(params or {})}
    return {"ok": True, "url": auth_url + "?" + urllib.parse.urlencode(q), "tier": tier}


def exchange_code(m, code: str, state: str, key_of) -> dict:
    """Callback: swap `code` for tokens using the pending `state`. `key_of(pending)` names the account the
    tokens belong to. Returns {ok, provider, tier, pending} — the connector shapes its own answer."""
    import httpx
    data = m._load()
    pend = (data.get("pending", {}) or {}).pop(state, None)
    m._save(data)
    if not pend:
        return {"ok": False, "error": "state desconocido o caducado"}
    p = m._pv.get(pend.get("provider") or "")
    if not _capable(m, p):
        return {"ok": False, "error": "proveedor inválido"}
    _auth_url, token_url, _scopes, _extra = _spec(m, p, pend.get("tier") or "")
    body = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": pend.get("redirect") or m.redirect_uri(),
            "client_id": m.client_id(p.id), "code_verifier": pend["verifier"]}
    sec = m.client_secret(p.id)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:  # noqa: BLE001 — the provider's failure is reported, not raised
        return {"ok": False, "error": f"intercambio falló: {e}"}
    if "access_token" not in tok:
        return {"ok": False, "error": f"sin access_token: "
                                      f"{tok.get('error_description') or tok.get('error') or tok}"}
    tier = pend.get("tier") or getattr(p, "default_tier", "") or ""
    store_tokens(m, key_of(pend), tier, tok)
    return {"ok": True, "provider": p.id, "tier": tier, "pending": pend}


def access_token(m, provider_id: str, key: str, acct: dict) -> str | None:
    """A VALID access token (refreshed when it is about to expire) or None, for the account `acct` stored under
    `key` (read by the connector, through its own `account`). On a failed refresh the stale token is returned
    rather than nothing, as every copy did — the caller's request then fails visibly."""
    import httpx
    if not acct:
        return None
    if acct.get("access_token") and int(acct.get("expires_at", 0) or 0) - REFRESH_SKEW > time.time():
        return acct["access_token"]
    rt = acct.get("refresh_token")
    p = m._pv.get(provider_id)
    if not rt or not _capable(m, p):
        return acct.get("access_token") or None
    _auth_url, token_url, scopes, _extra = _spec(m, p, acct.get("tier") or "")
    body = {"grant_type": "refresh_token", "refresh_token": rt, "client_id": m.client_id(provider_id),
            "scope": " ".join(scopes)}
    sec = m.client_secret(provider_id)
    if sec:
        body["client_secret"] = sec
    try:
        r = httpx.post(token_url, data=body, timeout=30)
        tok = r.json()
    except Exception as e:  # noqa: BLE001
        m.logger.warning(f"{m.ENV_PREFIX.lower()} oauth refresh failed ({provider_id}): {e}")
        return acct.get("access_token") or None
    if "access_token" in tok:
        store_tokens(m, key, acct.get("tier") or "", tok)
        return tok["access_token"]
    return acct.get("access_token") or None
