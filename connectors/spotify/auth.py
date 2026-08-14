"""connectors/spotify/auth.py — OAuth 2.0 (Authorization Code + PKCE) for Spotify (V2-041).

Spotify controls playback with a USER token. The flow is PKCE (S256, NO client-secret: safe for an installed app)
and is served by zaelar's own server (`server/spotify_api.py`) — not a separate HTTP thread like in the Hermes donor:
the redirect returns to `http://127.0.0.1:<port>/api/spotify/callback`, which is ALREADY our endpoint.

UI-managed config (product invariant):
  · `SPOTIFY_CLIENT_ID` lives in the credential store (`config/credentials.py`, chmod 600). The client_id is NOT a
    secret in PKCE (it is public), but it is stored with the rest so config has one home.
  · TOKENS (access/refresh, rotating) live in `.meshkore/credentials/spotify.json` (gitignored, chmod 600) — NEVER in
    the repo, NEVER to the frontend (public view is presence-only).

All functions are SYNCHRONOUS and FAIL-SAFE (return {ok:False,...} or None, never raise to the caller).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
import urllib.parse
from pathlib import Path

import httpx

logger = logging.getLogger("zaelar.music.spotify")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _ROOT / ".meshkore" / "credentials" / "spotify.json"

_ACCOUNTS = "https://accounts.spotify.com"
_SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
_REFRESH_SKEW = 120                          # refresh 2 min before expiry
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/spotify/callback"

# client_id for the zaelar APP (PKCE -> client_id is NOT secret): if filled here or through
# SPOTIFY_DEFAULT_CLIENT_ID, the user connects with ONE CLICK (only signs in with their own Spotify account), without
# registering any developer app. This is the SHORTEST path for the end user. It stays empty until the operator
# registers the zaelar app on developer.spotify.com (once) and puts its client_id here — then ALL users get "connect
# with one click". The widget's "use your own app" field is the fallback.
# (Spotify limits a Development-mode app to 25 users; multi-user SaaS requires Extended Quota.)
# App "jarvenn" (developer.spotify.com, operator Premium account, registered 2026-07-15 — Web API enabled, unblocked).
# The client_id is PUBLIC in PKCE (appears in every /authorize URL) -> safe in the repo. client_SECRET is NOT used or
# stored (PKCE does not need it).
_DEFAULT_CLIENT_ID = "7feacada544247f693812e78cb7878c2"

_lock = threading.Lock()


# ── config (client_id / redirect) ────────────────────────────────────────────────────────────────────────
def client_id() -> str:
    """Effective client_id: user-provided (credential store) -> env -> zaelar DEFAULT (one click)."""
    try:
        from config import credentials
        cid = credentials.get("SPOTIFY_CLIENT_ID")
        if cid:
            return cid.strip()
    except Exception:
        pass
    return ((os.getenv("SPOTIFY_CLIENT_ID") or "").strip()
            or (os.getenv("SPOTIFY_DEFAULT_CLIENT_ID") or "").strip()
            or _DEFAULT_CLIENT_ID.strip())


def has_default_client_id() -> bool:
    """Is there a zaelar client_id (default) -> user can connect with ONE CLICK without registering their own app?"""
    return bool((os.getenv("SPOTIFY_DEFAULT_CLIENT_ID") or "").strip() or _DEFAULT_CLIENT_ID.strip())


def user_client_id_set() -> bool:
    """Did the user set THEIR OWN client_id (credential store / env), apart from zaelar's default?"""
    try:
        from config import credentials
        if (credentials.get("SPOTIFY_CLIENT_ID") or "").strip():
            return True
    except Exception:
        pass
    return bool((os.getenv("SPOTIFY_CLIENT_ID") or "").strip())


def redirect_uri() -> str:
    return (os.getenv("SPOTIFY_REDIRECT_URI") or _DEFAULT_REDIRECT).strip()


# ── token store (chmod 600, atomic) ──────────────────────────────────────────────────────────────────────
def _load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    with _lock:
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(STORE) + ".tmp"
            Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.chmod(tmp, 0o600)             # secret before replace (no 644 window)
            os.replace(tmp, STORE)
            try:
                os.chmod(STORE, 0o600)
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"no pude guardar tokens de Spotify: {e!r}")


# ── PKCE ─────────────────────────────────────────────────────────────────────────────────────────────────
def _verifier() -> str:
    raw = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii")
    return raw.rstrip("=")[:128]


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# ── login (2 steps: authorize URL -> callback) ───────────────────────────────────────────────────────────
def begin_login() -> dict:
    """Step 1: generate verifier/challenge/state, save them as `pending`, and return the authorization URL opened by
    the frontend in a window. `{ok, url}` or `{ok:False, error}`."""
    cid = client_id()
    if not cid:
        return {"ok": False, "error": "no_client_id"}
    verifier = _verifier()
    state = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")
    data = _load()
    data["pending"] = {"verifier": verifier, "state": state, "ts": int(time.time())}
    _save(data)
    params = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": _SCOPE,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": _challenge(verifier),
    }
    return {"ok": True, "url": f"{_ACCOUNTS}/authorize?" + urllib.parse.urlencode(params)}


def complete_login(code: str, state: str) -> dict:
    """Step 2 (callback): verify `state`, exchange `code` for tokens using the saved verifier, persist. `{ok}` or
    `{ok:False, error}`."""
    data = _load()
    pending = data.get("pending") or {}
    if not pending or not state or pending.get("state") != state:
        return {"ok": False, "error": "state_mismatch"}
    if not code:
        return {"ok": False, "error": "no_code"}
    try:
        r = httpx.post(f"{_ACCOUNTS}/api/token", data={
            "client_id": client_id(),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "code_verifier": pending.get("verifier", ""),
        }, timeout=15)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"network:{e}"[:120]}
    if r.status_code >= 400:
        return {"ok": False, "error": f"token_exchange_{r.status_code}", "detail": r.text[:200]}
    tok = r.json()
    now = int(time.time())
    data.pop("pending", None)
    data["tokens"] = {
        "access_token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token", ""),
        "token_type": tok.get("token_type", "Bearer"),
        "scope": tok.get("scope", _SCOPE),
        "expires_at": now + int(tok.get("expires_in", 3600)),
        "obtained_at": now,
    }
    _save(data)
    return {"ok": True}


def _refresh(tokens: dict) -> dict:
    """Refresh the access_token with the refresh_token. Return updated tokens or {} if it fails."""
    rt = tokens.get("refresh_token", "")
    if not rt:
        return {}
    try:
        r = httpx.post(f"{_ACCOUNTS}/api/token", data={
            "grant_type": "refresh_token", "refresh_token": rt, "client_id": client_id(),
        }, timeout=15)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"refresh Spotify falló (red): {e!r}")
        return {}
    if r.status_code >= 400:
        logger.warning(f"refresh Spotify {r.status_code}: {r.text[:120]}")
        return {}
    tok = r.json()
    now = int(time.time())
    updated = dict(tokens)
    updated["access_token"] = tok.get("access_token", tokens.get("access_token", ""))
    updated["refresh_token"] = tok.get("refresh_token") or rt      # refresh may not return a new one
    updated["expires_at"] = now + int(tok.get("expires_in", 3600))
    updated["obtained_at"] = now
    return updated


def access_token() -> str:
    """Return a VALID access_token (refreshes if it is about to expire). '' if there is no session."""
    data = _load()
    tokens = data.get("tokens") or {}
    if not tokens.get("access_token") and not tokens.get("refresh_token"):
        return ""
    if int(time.time()) >= int(tokens.get("expires_at", 0)) - _REFRESH_SKEW:
        updated = _refresh(tokens)
        if updated:
            data["tokens"] = updated
            _save(data)
            tokens = updated
        elif int(time.time()) >= int(tokens.get("expires_at", 0)):
            return ""                                              # expired and could not refresh
    return tokens.get("access_token", "")


def logged_in() -> bool:
    tokens = _load().get("tokens") or {}
    return bool(tokens.get("refresh_token") or tokens.get("access_token"))


def disconnect() -> dict:
    """Delete tokens (leave client_id in the credential store to reconnect without pasting it again)."""
    data = _load()
    data.pop("tokens", None)
    data.pop("pending", None)
    _save(data)
    return {"ok": True}


def status() -> dict:
    """PUBLIC (redacted) view: client_id presence + whether a session exists. NEVER the token.
    `can_connect` = some client_id exists (zaelar default or own) -> the "Connect" button already works without
    asking for anything. `own_client_id_set` = user provided their own. `default_available` = zaelar ships a built-in
    client_id."""
    return {"client_id_set": bool(client_id()), "logged_in": logged_in(),
            "can_connect": bool(client_id()), "own_client_id_set": user_client_id_set(),
            "default_available": has_default_client_id(), "redirect_uri": redirect_uri()}
