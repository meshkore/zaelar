"""connectors/spotify/auth.py — OAuth 2.0 (Authorization Code + PKCE) para Spotify (V2-041).

Spotify controla la reproducción con un token de USUARIO. El flujo es PKCE (S256, SIN client-secret: seguro para
una app instalada) y lo sirve el propio servidor de zaelar (`server/spotify_api.py`) — no un hilo HTTP aparte como
en el donante Hermes: el redirect vuelve a `http://127.0.0.1:<puerto>/api/spotify/callback`, que YA es un endpoint
nuestro.

Config gestionada por la UI (invariante de producto):
  · `SPOTIFY_CLIENT_ID` vive en el credential store (`config/credentials.py`, chmod 600). El client_id NO es un
    secreto en PKCE (es público), pero se guarda junto al resto para un solo sitio de config.
  · Los TOKENS (access/refresh, rotan) viven en `.meshkore/credentials/spotify.json` (gitignored, chmod 600) —
    NUNCA en el repo, NUNCA al frontend (la vista pública es solo-presencia).

Todas las funciones son SÍNCRONAS y FAIL-SAFE (devuelven {ok:False,...} o None, nunca lanzan al llamante).
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
_REFRESH_SKEW = 120                          # refresca 2 min antes de caducar
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/spotify/callback"

# client_id de la APP de zaelar (PKCE → el client_id NO es secreto): si se rellena (aquí o por
# SPOTIFY_DEFAULT_CLIENT_ID), el usuario conecta con UN CLIC (solo inicia sesión con su propia cuenta de Spotify),
# sin registrar ninguna app de developer. Es el camino MÁS CORTO para el usuario final. Se deja vacío hasta que el
# operador registre la app de zaelar en developer.spotify.com (una vez) y ponga aquí su client_id — momento en el
# que TODOS los usuarios tienen "conectar con un clic". El campo "usa tu propia app" del widget es el fallback.
# (Spotify limita una app en modo Development a 25 usuarios; para SaaS multiusuario se pide Extended Quota.)
# App "jarvenn" (developer.spotify.com, cuenta Premium del operador, registrada 2026-07-15 — Web API habilitada,
# sin bloqueo). El client_id es PÚBLICO en PKCE (sale en cada URL de /authorize) → seguro en el repo. El
# client_SECRET NO se usa ni se guarda (PKCE no lo necesita).
_DEFAULT_CLIENT_ID = "7feacada544247f693812e78cb7878c2"

_lock = threading.Lock()


# ── config (client_id / redirect) ────────────────────────────────────────────────────────────────────────
def client_id() -> str:
    """client_id efectivo: el que puso el usuario (credential store) → env → el DEFAULT de zaelar (un clic)."""
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
    """¿Hay un client_id de zaelar (default) → el usuario puede conectar con UN CLIC sin registrar app propia?"""
    return bool((os.getenv("SPOTIFY_DEFAULT_CLIENT_ID") or "").strip() or _DEFAULT_CLIENT_ID.strip())


def user_client_id_set() -> bool:
    """¿El usuario puso SU PROPIO client_id (credential store / env), aparte del default de zaelar?"""
    try:
        from config import credentials
        if (credentials.get("SPOTIFY_CLIENT_ID") or "").strip():
            return True
    except Exception:
        pass
    return bool((os.getenv("SPOTIFY_CLIENT_ID") or "").strip())


def redirect_uri() -> str:
    return (os.getenv("SPOTIFY_REDIRECT_URI") or _DEFAULT_REDIRECT).strip()


# ── token store (chmod 600, atómico) ─────────────────────────────────────────────────────────────────────
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
            os.chmod(tmp, 0o600)             # secreto antes del replace (sin ventana 644)
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


# ── login (2 pasos: authorize URL → callback) ────────────────────────────────────────────────────────────
def begin_login() -> dict:
    """Paso 1: genera verifier/challenge/state, los guarda como `pending`, y devuelve la URL de autorización que
    el frontend abre en una ventana. `{ok, url}` o `{ok:False, error}`."""
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
    """Paso 2 (callback): verifica el `state`, canjea el `code` por tokens con el verifier guardado, persiste.
    `{ok}` o `{ok:False, error}`."""
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
    """Refresca el access_token con el refresh_token. Devuelve los tokens actualizados o {} si falla."""
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
    updated["refresh_token"] = tok.get("refresh_token") or rt      # el refresh puede no devolver uno nuevo
    updated["expires_at"] = now + int(tok.get("expires_in", 3600))
    updated["obtained_at"] = now
    return updated


def access_token() -> str:
    """Devuelve un access_token VÁLIDO (refresca si está a punto de caducar). '' si no hay sesión."""
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
            return ""                                              # caducado y no se pudo refrescar
    return tokens.get("access_token", "")


def logged_in() -> bool:
    tokens = _load().get("tokens") or {}
    return bool(tokens.get("refresh_token") or tokens.get("access_token"))


def disconnect() -> dict:
    """Borra los tokens (deja el client_id en el credential store para reconectar sin re-pegarlo)."""
    data = _load()
    data.pop("tokens", None)
    data.pop("pending", None)
    _save(data)
    return {"ok": True}


def status() -> dict:
    """Vista PÚBLICA (redactada): presencia de client_id + si hay sesión. NUNCA el token.
    `can_connect` = hay algún client_id (default de zaelar o propio) → el botón "Conectar" ya funciona sin pedir nada.
    `own_client_id_set` = el usuario puso el suyo. `default_available` = zaelar trae un client_id de fábrica."""
    return {"client_id_set": bool(client_id()), "logged_in": logged_in(),
            "can_connect": bool(client_id()), "own_client_id_set": user_client_id_set(),
            "default_available": has_default_client_id(), "redirect_uri": redirect_uri()}
