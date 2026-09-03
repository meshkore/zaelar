#
# google_photos.py — Google Photos PICKER API v1 client (V2-564). Speaks HTTP to
# `photospicker.googleapis.com` and returns plain dicts; knows nothing about widgets, prompts or the brain.
#
# ── THE PART THAT MAKES THIS DIFFERENT FROM A NORMAL FILE BROWSER ─────────────────────────────────────────
#
# There is no "list the library" call. The shape is: create a SESSION → send the operator to `pickerUri` in a
# new tab → poll the session until `mediaItemsSet` is true → list that session's `mediaItems` → download a
# THUMBNAIL for each one WHILE its `baseUrl` is still valid.
#
# `baseUrl` is a signed, time-limited link (Google states roughly an hour) — it is NOT something to store and
# reuse later. If the caller needs a fresh one after it has expired, the only way is to re-list the session's
# media items, and a session itself eventually expires too (`expireTime` on the session object). This is why
# `service.py` downloads and keeps a small local thumbnail at IMPORT time rather than storing `baseUrl` in
# `store.py` — a gallery whose thumbnails silently 404 an hour after import would be worse than the wall this
# whole connector already has to work around.
#
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.photos.google")

_API = "https://photospicker.googleapis.com/v1"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_session(token: str) -> dict:
    """{id, picker_uri, expire_time, poll_interval_s} for a fresh picking session."""
    import httpx
    r = httpx.post(f"{_API}/sessions", headers=_headers(token), json={}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"photos picker session {r.status_code}: {r.text[:200]}")
    d = r.json()
    poll_cfg = d.get("pollingConfig") or {}
    return {
        "id": str(d.get("id") or ""),
        "picker_uri": str(d.get("pickerUri") or ""),
        "expire_time": str(d.get("expireTime") or ""),
        "poll_interval_s": _duration_s(poll_cfg.get("pollInterval")) or 5,
        "media_items_set": bool(d.get("mediaItemsSet")),
    }


def get_session(token: str, session_id: str) -> dict:
    """Poll one session's completion state. Same shape as `create_session`'s result."""
    import httpx
    import urllib.parse
    sid = urllib.parse.quote(str(session_id))
    r = httpx.get(f"{_API}/sessions/{sid}", headers=_headers(token), timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"photos picker session {r.status_code}: {r.text[:200]}")
    d = r.json()
    poll_cfg = d.get("pollingConfig") or {}
    return {
        "id": str(d.get("id") or ""),
        "picker_uri": str(d.get("pickerUri") or ""),
        "expire_time": str(d.get("expireTime") or ""),
        "poll_interval_s": _duration_s(poll_cfg.get("pollInterval")) or 5,
        "media_items_set": bool(d.get("mediaItemsSet")),
    }


def delete_session(token: str, session_id: str) -> None:
    """Best-effort cleanup once a session's items are imported. Never raises — a leaked session on Google's
    side costs nothing the operator can see, and is not worth a failed import over."""
    import httpx
    import urllib.parse
    try:
        sid = urllib.parse.quote(str(session_id))
        httpx.delete(f"{_API}/sessions/{sid}", headers=_headers(token), timeout=15)
    except Exception as e:
        logger.debug(f"photos picker session delete failed (harmless): {e}")


def list_media_items(token: str, session_id: str, page_token: str = "", limit: int = 100) -> dict:
    """{items, next} — the RAW picker media items for one session (one page). `items` keep Google's own field
    names; `service.py` normalizes them."""
    import httpx
    params = {"sessionId": session_id, "pageSize": max(1, min(int(limit or 100), 100))}
    if page_token:
        params["pageToken"] = page_token
    r = httpx.get(f"{_API}/mediaItems", headers=_headers(token), params=params, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"photos picker mediaItems {r.status_code}: {r.text[:200]}")
    d = r.json()
    return {"items": d.get("mediaItems") or [], "next": str(d.get("nextPageToken") or "")}


def download_bytes(url: str, timeout: int = 30) -> bytes:
    """The raw bytes at an already-sized `baseUrl` (caller appends `=w<N>-h<N>` first). No token needed — the
    signed URL carries its own authorization."""
    import httpx
    r = httpx.get(url, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"photos picker download {r.status_code}")
    return r.content


def thumb_url(base_url: str, size: int = 512) -> str:
    """`baseUrl` needs a size suffix to return actual bytes instead of metadata. `=w{N}-h{N}` fits the image
    inside an NxN box preserving aspect ratio — Google's own documented pattern."""
    b = str(base_url or "").rstrip("/")
    return f"{b}=w{int(size)}-h{int(size)}" if b else ""


def _duration_s(v) -> float:
    """`pollingConfig.pollInterval` comes back as a protobuf Duration string like "5s". Best-effort parse; a
    bad/missing value falls back to the caller's own default rather than raising."""
    s = str(v or "").strip()
    if s.endswith("s"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0
