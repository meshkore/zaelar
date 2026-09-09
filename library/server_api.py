"""server_api.py — the agent's own filesystem over HTTP, at `/api/library/*` (V2-638). Loopback.

Prefix checked free before choosing it (`grep -rn '"/api/library' server/ connectors/ widgets/` → nothing).

`GET /api/library/stream` is the ONE route both players use for a local file — the video widget's `<video>`
and the music widget's `<audio>` point at the same place, because a file on disk is a file on disk and two
routes doing this would drift. Starlette's `FileResponse` implements Range/`206` natively, which is all a
finished file needs (a still-DOWNLOADING torrent is the other case, and it has its own piece-aware route in
`connectors/torrent`).

Every path arriving here is untrusted (a query string). Nothing dereferences it directly: `paths.resolve()` is
the only door and it answers `None` for anything outside the library, symlinks included.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from library import formats, index, paths

router = APIRouter()


@router.get("/api/library/rules")
async def rules():
    """The structure: root, folder per kind, the guide, and the download policy."""
    return JSONResponse({"ok": True, **paths.rules()})


@router.post("/api/library/rules")
async def set_rules(payload: dict | None = None):
    """The operator renames a folder / moves the root / flips the playable-only policy."""
    return JSONResponse(paths.set_overrides(payload or {}))


@router.get("/api/library/list")
async def listing(kind: str = "", playable_only: bool = False, limit: int = index.MAX_ENTRIES):
    return JSONResponse({"ok": True,
                         "items": index.listing(kind, limit=max(1, min(int(limit or 1), index.MAX_ENTRIES)),
                                                playable_only=bool(playable_only)),
                         "rules": paths.rules()})


@router.get("/api/library/summary")
async def summary():
    return JSONResponse(index.summary())


@router.get("/api/library/stream")
async def stream(path: str = ""):
    """Play a library file. FileResponse answers `Range:` with a `206` on its own, which is what lets a
    `<video>`/`<audio>` seek. A file the browser cannot decode is REFUSED here rather than served as a black
    rectangle — it is offered through /download instead, which is the honest affordance for it."""
    p = paths.resolve(path)
    if p is None or not p.is_file():
        return JSONResponse({"ok": False, "error": "no such file"}, status_code=404)
    if not formats.browser_playable(p.name):
        return JSONResponse({"ok": False, "error": "not playable in the browser",
                             "download_url": index.download_url(paths.rel_of(p))}, status_code=415)
    return FileResponse(p, media_type=formats.mime_of(p.name),
                        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"})


@router.get("/api/library/download")
async def download(path: str = ""):
    """Hand the FILE over — the operator's «lo quiero para el pendrive» case. Any format, playable or not."""
    p = paths.resolve(path)
    if p is None or not p.is_file():
        return JSONResponse({"ok": False, "error": "no such file"}, status_code=404)
    return FileResponse(p, media_type=formats.mime_of(p.name), filename=p.name)
