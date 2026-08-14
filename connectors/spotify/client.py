"""connectors/spotify/client.py — REST client for the Spotify Web API (V2-041).

Thin SYNCHRONOUS wrapper (httpx) around the endpoints voice playback needs: search for a track and control the
operator's player (play/pause/next/prev/volume/state). Token is resolved by `connectors.spotify.auth` (automatic
refresh). Covers only what we use — not a full SDK.

API notes (all verified against official docs):
  · Controlling playback requires **Premium + an active Spotify Connect device**. Without an active device,
    `PUT /me/player/play` returns **404 NO_ACTIVE_DEVICE** -> the provider resolves it by finding a device and
    passing `device_id` (or asking the operator to open Spotify).
  · Search (`/search`) works with any user token, with no special scope.
"""
from __future__ import annotations

import httpx

from . import auth

_API = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    def __init__(self, status: int, code: str = "", message: str = ""):
        self.status = status
        self.code = code                     # stable: no_device | premium | auth | rate_limit | http
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
        return "premium"                     # playback control without Premium
    return "http"


def _request(method: str, path: str, *, params: dict = None, json_body: dict = None, retry_401: bool = True):
    """Raw request. Returns JSON (or {} on 204). Raises SpotifyError on >=400 (with stable code)."""
    url = _API + path
    params = {k: v for k, v in (params or {}).items() if v is not None}
    json_body = {k: v for k, v in (json_body or {}).items() if v is not None} or None
    try:
        r = httpx.request(method, url, headers=_headers(), params=params, json=json_body, timeout=15)
    except httpx.HTTPError as e:
        raise SpotifyError(0, "http", str(e)[:120])
    if r.status_code == 401 and retry_401:
        auth.access_token()                  # force refresh and retry once
        return _request(method, path, params=params, json_body=json_body, retry_401=False)
    if r.status_code >= 400:
        raise SpotifyError(r.status_code, _classify(r.status_code, path, r.text), r.text[:160])
    if r.status_code == 204 or not r.content:
        return {}
    try:
        return r.json()
    except Exception:
        return {}


# ── search ───────────────────────────────────────────────────────────────────────────────────────────────
def search(query: str, types: str = "track", limit: int = 5) -> dict:
    return _request("GET", "/search", params={"q": query, "type": types, "limit": limit})


# ── devices ──────────────────────────────────────────────────────────────────────────────────────────────
def devices() -> list:
    return (_request("GET", "/me/player/devices") or {}).get("devices", [])


def transfer(device_id: str, play: bool = True) -> dict:
    return _request("PUT", "/me/player", json_body={"device_ids": [device_id], "play": play})


# ── playback ─────────────────────────────────────────────────────────────────────────────────────────────
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
