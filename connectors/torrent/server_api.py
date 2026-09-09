"""server_api.py — the torrent add-on's HTTP surface, at `/api/torrent/*` (V2-637). Loopback, like the rest.

Prefix checked free before choosing it (`grep -rn '"/api/torrent' server/ connectors/` → nothing): two routers
on one prefix is a collision FastAPI resolves by mount order, silently (V2-557 T10).

The one endpoint that is not trivial is `GET /api/torrent/stream/{id}`. The video file is still DOWNLOADING, so
Starlette's `FileResponse` (which stats the file once and trusts that size) cannot serve it — a `<video>` seeks
with `Range:` and expects a `206` whose `Content-Range` reflects the FULL file size, not how much has arrived.
So this hand-rolls the 206 over `session.iter_range`, which blocks per-chunk until the pieces it is about to
send are on disk. A chunk that never arrives raises inside the generator and closes the stream — a browser
retries a Range far better than it survives a socket that hangs open forever.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from connectors.torrent import service, session

router = APIRouter()

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@router.get("/api/torrent/status")
async def status_all():
    return JSONResponse({"ok": True, "available": service.available(), "items": service.active()})


@router.get("/api/torrent/status/{rid}")
async def status_one(rid: str):
    return JSONResponse(service.status(rid))


@router.post("/api/torrent/add")
async def add(payload: dict | None = None):
    payload = payload or {}
    magnet = str(payload.get("magnet") or "").strip()
    if magnet:
        return JSONResponse(service.add_magnet(magnet))
    query = str(payload.get("query") or "").strip()
    return JSONResponse(service.search_and_play(query))


@router.post("/api/torrent/remove")
async def remove(payload: dict | None = None):
    payload = payload or {}
    return JSONResponse(service.remove(str(payload.get("id") or "")))


def _parse_range(header: str, size: int):
    """(start, end_inclusive) from a `Range:` header, clamped to the file. None → serve from 0."""
    if not header:
        return None
    m = _RANGE_RE.search(header or "")
    if not m:
        return None
    lo, hi = m.group(1), m.group(2)
    if lo == "" and hi == "":
        return None
    if lo == "":                       # suffix range: last N bytes
        n = min(int(hi), size)
        return max(0, size - n), size - 1
    start = int(lo)
    end = int(hi) if hi else size - 1
    start = max(0, min(start, size - 1))
    end = max(start, min(end, size - 1))
    return start, end


@router.get("/api/torrent/stream/{rid}")
async def stream(rid: str, request: Request):
    """Stream the chosen video with HTTP Range, so a `<video>` can play and seek while it downloads."""
    info = session.file_info(rid)
    if not info.get("ok"):
        return JSONResponse(info, status_code=404)
    size, mime = info["size"], info["mime"]
    rng = _parse_range(request.headers.get("range", ""), size)
    if rng is None:
        start, end, code = 0, size - 1, 200
    else:
        start, end, code = rng[0], rng[1], 206
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": mime,
        "Cache-Control": "no-store",
    }
    if code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def body():
        try:
            yield from session.iter_range(rid, start, length)
        except (TimeoutError, FileNotFoundError, OSError):
            return   # close the stream; the browser re-requests the Range it still needs

    return StreamingResponse(body(), status_code=code, headers=headers, media_type=mime)
