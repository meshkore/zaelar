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


# ── WHERE the library lives — the first-run folder step, self-host only (V2-672) ──────────────────────────
# The operator picks a folder once, at onboarding, and every download and generated file lands under it.
# A CLOUD account gets neither route: there the Volume IS the storage, the process has no desktop to draw a
# dialog on, and offering the question would be offering a choice that cannot be honoured.

def _folder_step_allowed() -> bool:
    from nucleo import cloud_account
    return not cloud_account.is_cloud_account()


@router.get("/api/library/base")
async def base_state():
    """What the folder step needs to paint itself: where the files go now, whether this deployment may
    change it, and whether a native picker can actually be drawn on this machine."""
    from library import folder_dialog
    allowed = _folder_step_allowed()
    return JSONResponse({"ok": True, "base": str(paths.base()), "root": str(paths.root()),
                         "can_choose": allowed,
                         "has_dialog": bool(allowed and folder_dialog.available())})


@router.post("/api/library/base/browse")
async def base_browse():
    """Open the OS folder picker. Best effort: `{"ok": false, "reason": "unavailable"}` when this machine
    has no picker, which is a normal answer and not a failure — the caller falls back to a typed path."""
    if not _folder_step_allowed():
        return JSONResponse({"ok": False, "reason": "not_available_here"}, status_code=403)
    from library import folder_dialog
    return JSONResponse(folder_dialog.choose())


@router.post("/api/library/base")
async def set_base(payload: dict | None = None):
    """Persist the chosen folder. An EMPTY value restores the default — the way back matters as much as the
    way in. Refusals carry their `reason` so the screen can say what is wrong with the folder (V2-559)."""
    if not _folder_step_allowed():
        return JSONResponse({"ok": False, "reason": "not_available_here"}, status_code=403)
    raw = str((payload or {}).get("base") or "").strip()
    res = paths.set_overrides({"base": raw})
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    try:
        paths.ensure()                    # create the tree where he put it, so the choice is visible at once
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True, "base": str(paths.base()), "root": str(paths.root())})


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
