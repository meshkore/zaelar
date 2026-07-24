"""connectors/spotify/client.py — cliente REST de la Spotify Web API (V2-041).

Envoltorio fino y SÍNCRONO (httpx) sobre los endpoints que necesita la reproducción por voz: buscar una pista y
controlar el reproductor del operador (play/pause/next/prev/volumen/estado). El token lo resuelve
`connectors.spotify.auth` (refresco automático). Solo cubre lo que usamos — no es un SDK completo.

Notas de la API (todas verificadas contra la doc oficial):
  · Controlar el reproductor exige **Premium + un dispositivo Spotify Connect activo**. Sin dispositivo activo,
    `PUT /me/player/play` responde **404 NO_ACTIVE_DEVICE** → el proveedor lo resuelve buscando un dispositivo y
    pasándole el `device_id` (o pidiendo al operador que abra Spotify).
  · La búsqueda (`/search`) funciona con cualquier token de usuario, sin scope especial.
"""
from __future__ import annotations

import httpx

from . import auth

_API = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    def __init__(self, status: int, code: str = "", message: str = ""):
        self.status = status
        self.code = code                     # estable: no_device | premium | auth | rate_limit | http
        self.message = message
        super().__init__(f"{status} {code}: {message}")


def _headers() -> dict:
    tok = auth.access_token()
    if not tok:
        raise SpotifyError(401, "auth", "sin sesión de Spotify")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _classify(status: int, path: str, body: str) -> str:
    if status == 401:
        return "auth"
    if status == 429:
        return "rate_limit"
    if status == 404 and "/me/player" in path:
        return "no_device"                   # NO_ACTIVE_DEVICE
    if status == 403 and "/me/player" in path:
        return "premium"                     # control de reproducción sin Premium
    return "http"


def _request(method: str, path: str, *, params: dict = None, json_body: dict = None, retry_401: bool = True):
    """Petición cruda. Devuelve el JSON (o {} en 204). Lanza SpotifyError en >=400 (con código estable)."""
    url = _API + path
    params = {k: v for k, v in (params or {}).items() if v is not None}
    json_body = {k: v for k, v in (json_body or {}).items() if v is not None} or None
    try:
        r = httpx.request(method, url, headers=_headers(), params=params, json=json_body, timeout=15)
    except httpx.HTTPError as e:
        raise SpotifyError(0, "http", str(e)[:120])
    if r.status_code == 401 and retry_401:
        auth.access_token()                  # fuerza refresco y reintenta una vez
        return _request(method, path, params=params, json_body=json_body, retry_401=False)
    if r.status_code >= 400:
        raise SpotifyError(r.status_code, _classify(r.status_code, path, r.text), r.text[:160])
    if r.status_code == 204 or not r.content:
        return {}
    try:
        return r.json()
    except Exception:
        return {}


# ── búsqueda ─────────────────────────────────────────────────────────────────────────────────────────────
def search(query: str, types: str = "track", limit: int = 5) -> dict:
    return _request("GET", "/search", params={"q": query, "type": types, "limit": limit})


# ── dispositivos ─────────────────────────────────────────────────────────────────────────────────────────
def devices() -> list:
    return (_request("GET", "/me/player/devices") or {}).get("devices", [])


def transfer(device_id: str, play: bool = True) -> dict:
    return _request("PUT", "/me/player", json_body={"device_ids": [device_id], "play": play})


# ── reproducción ─────────────────────────────────────────────────────────────────────────────────────────
def play(uris: list = None, context_uri: str = "", device_id: str = "") -> dict:
    body = {}
    if uris:
        body["uris"] = uris
    if context_uri:
        body["context_uri"] = context_uri
    return _request("PUT", "/me/player/play", params={"device_id": device_id or None}, json_body=body or None)


def pause(device_id: str = "") -> dict:
    return _request("PUT", "/me/player/pause", params={"device_id": device_id or None})


def resume(device_id: str = "") -> dict:
    return _request("PUT", "/me/player/play", params={"device_id": device_id or None})


def next_track(device_id: str = "") -> dict:
    return _request("POST", "/me/player/next", params={"device_id": device_id or None})


def previous_track(device_id: str = "") -> dict:
    return _request("POST", "/me/player/previous", params={"device_id": device_id or None})


def set_volume(percent: int, device_id: str = "") -> dict:
    return _request("PUT", "/me/player/volume",
                    params={"volume_percent": max(0, min(100, int(percent))), "device_id": device_id or None})


def playback_state() -> dict:
    return _request("GET", "/me/player") or {}
