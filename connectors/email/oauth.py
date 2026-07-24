#
# oauth.py — OAuth2 (authorization-code + PKCE) para el email, MODEL-AGNÓSTICO por proveedor (V2-055). Gmail y
# Outlook/Microsoft comparten el MISMO flujo (endpoints/scopes vienen del registro `providers.py`), y el transporte
# sigue siendo IMAP/SMTP con SASL XOAUTH2 (el access token sustituye a la contraseña, ver `mailbox.xoauth2_sasl`).
#
# Patrón calcado de `connectors/spotify/auth.py` (V2-041): PKCE S256 (sin exponer secret en apps instaladas), el
# callback lo sirve el PROPIO servidor de zaelar (`server/email_api.py` → /api/email/callback), tokens en el
# credential store (`.meshkore/credentials/email_oauth.json`, chmod 600, gitignored — NUNCA en el repo ni al
# frontend). Config gestionada por la UI: el `client_id`/`secret` de la app (Google Cloud / Microsoft Entra) los
# pone el operador UNA vez; DORMANTE hasta entonces (como Spotify).
#
# Todas las funciones son SÍNCRONAS y FAIL-SAFE (devuelven {ok:False,...} o None; nunca lanzan al llamante).
#
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path

from connectors.email import providers as _pv

logger = logging.getLogger("zaelar.email.oauth")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _ROOT / ".meshkore" / "credentials" / "email_oauth.json"
_REFRESH_SKEW = 120                      # refresca 2 min antes de caducar
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/email/callback"


# ── Credenciales de la app (credential store; dormante si vacías) ────────────────────────────────────────────────
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
    """¿Hay app OAuth registrada para este proveedor? (si no, el widget ofrece la vía app-password)."""
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return False
    return bool(client_id(provider_id))


def redirect_uri() -> str:
    return os.getenv("EMAIL_OAUTH_REDIRECT") or _DEFAULT_REDIRECT


# ── PKCE ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_pkce(seed: bytes | None = None) -> tuple[str, str]:
    """(verifier, challenge S256). `seed` inyectable para tests deterministas; en producción = os.urandom."""
    verifier = _b64url(seed if seed is not None else os.urandom(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# ── Store de tokens + pendientes (por proveedor:cuenta) ──────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        if STORE.exists():
            return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(STORE) + ".tmp"
        Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, STORE)
        try:
            os.chmod(STORE, 0o600)
        except OSError:
            pass
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


# ── Flujo authorization-code ─────────────────────────────────────────────────────────────────────────────────────
def authorize_url(provider_id: str, address: str = "") -> dict:
    """Devuelve {ok, url} — la URL de consentimiento a la que mandar al usuario. Stashea el verifier PKCE + el
    proveedor/cuenta bajo un `state` aleatorio (para el callback)."""
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return {"ok": False, "error": f"proveedor sin OAuth: {provider_id}"}
    cid = client_id(provider_id)
    if not cid:
        return {"ok": False, "error": f"sin app OAuth registrada para {p.label} (falta EMAIL_{provider_id.upper()}_CLIENT_ID)"}
    verifier, challenge = make_pkce()
    state = _b64url(os.urandom(18))
    data = _load()
    data.setdefault("pending", {})[state] = {"provider": provider_id, "address": address,
                                             "verifier": verifier, "ts": int(time.time())}
    _save(data)
    params = {
        "client_id": cid, "response_type": "code", "redirect_uri": redirect_uri(),
        "scope": " ".join(p.oauth.scopes), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",       # Google: fuerza refresh_token; Microsoft lo ignora
    }
    if address:
        params["login_hint"] = address
    return {"ok": True, "url": p.oauth.authorize_url + "?" + urllib.parse.urlencode(params)}


def exchange_code(code: str, state: str) -> dict:
    """Callback: canjea el `code` por tokens usando el `state` pendiente. Guarda access/refresh/expiry por cuenta.
    Devuelve {ok, provider, address}."""
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
        # el refresh_token no siempre vuelve en un refresh → conserva el anterior
        "refresh_token": tok.get("refresh_token") or cur.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)),
    }
    accts[_acct_key(provider_id, address)] = entry
    _save(data)


def access_token(provider_id: str, address: str) -> str | None:
    """Devuelve un access token VÁLIDO (refrescándolo si caducó) o None. Lo usa el conector para XOAUTH2."""
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
