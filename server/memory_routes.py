#
# server/memory_routes.py — HTTP for episodic memory (V2-003 · T54).
#
# ⚠️ IT LIVED IN `memory/server_api.py` until the architecture audit of 2026-08-23, and from there it imported
# `nucleo.dispatch` and `nucleo.memory_agent`: the TWO most serious reverse imports in the memory package (dispatch
# drags in half the engine). They were not a leak to plug; they were the signal that this file is not memory — it is
# TRANSPORT. A FastAPI router that verifies a worker's token against the dispatcher's registry belongs in
# the server layer by definition, and there those imports are the NORMAL direction. The memory package remains
# autonomous without losing anything: memory is still what does the resolving, this only exposes it over HTTP.
#
# Replaces files/server_api.py: the
# operator pastes an image or drags a file onto the frontend (frontend/app/main.js), and it lands here. Instead of
# the old flat files/uploads/ tray plus a [SYSTEM] note containing the path (which was for Hermes file
# tools), the binary now goes to EPISODIC memory (bytes in the data directory, searchable embedded summary) →
# the brain's retriever finds it on its own, without an absolute path or Hermes tools. No auth: the same
# trust model as the rest of the local API.
#
import asyncio
import threading
import os
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import ClientDisconnect

from files import attachments as _att
from memory import api as memapi
from .memory_recall import _recall_sync  # noqa: F401 — moved, imported back under its name

router = APIRouter()


def _refuse(status: int, reason: str, **extra) -> JSONResponse:
    """A refusal the composer can TRANSLATE: a stable `reason` code, never a sentence in one language."""
    return JSONResponse({"ok": False, "reason": reason, **extra}, status_code=status)


async def _chunks(request: Request):
    """The body as it arrives: a raw body is streamed from the socket; a multipart form (the desktop drop) has
    already been spooled by the parser and is copied out in chunks — never `read()` whole."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        up = form.get("file")
        if up is None or not hasattr(up, "read"):
            raise HTTPException(400, "file missing")
        request.state.filename = up.filename or "archivo"
        request.state.source = str(form.get("source") or "drop")
        size = int(_att.limits()["chunk_bytes"])
        while True:
            piece = await up.read(size)
            if not piece:
                break
            yield piece
        return
    async for piece in request.stream():
        if piece:
            yield piece


@router.post("/api/files/upload")
async def upload(request: Request):
    """THE upload door (the desktop drop, the paste, the chat's 📎 — V2-809). The body is STREAMED to a file in
    the episodic inbox, chunk by chunk, so RAM does not grow with the file. Two encodings, one door: a multipart
    form (`file` + `source`), or a raw body with the name in `X-File-Name` (URL-encoded) and `?source=` — the raw
    one is what lets the size and the disk headroom be refused BEFORE a byte is written.

    Refusals carry a `reason` the client translates: `too_large` (413), `type` (415), `disk_full` (507),
    `cancelled` (499, the client went away). `source=chat` additionally sniffs the kind from the bytes (image,
    PDF, text), reads the file with bounded work off the event loop, keeps a thumbnail, and makes it the turn's
    attachment (`files/attachments.py`)."""
    lim = _att.limits()
    max_bytes = int(lim["max_file_bytes"])
    request.state.filename = unquote(request.headers.get("x-file-name", "")) or "archivo"
    request.state.source = request.query_params.get("source", "drop")
    inbox = Path(memapi.episode_inbox())
    declared = request.headers.get("content-length")
    is_raw = not request.headers.get("content-type", "").startswith("multipart/form-data")
    announced = int(declared) if is_raw and declared and declared.isdigit() else 0
    if announced > max_bytes:
        return _refuse(413, "too_large", limit=max_bytes)
    if not _att.disk_allows(inbox, announced):
        return _refuse(507, "disk_full")
    held = _att.Reservation(announced)      # counted by every other upload's check until this one is written

    tmp = inbox / f"{uuid.uuid4().hex}.part"
    written, head, kind, mime, complete = 0, b"", None, None, False
    every = int(lim["chunk_bytes"]) * 16
    try:
        with open(tmp, "wb") as fh:
            async for piece in _chunks(request):
                written += len(piece)
                if written > max_bytes:
                    return _refuse(413, "too_large", limit=max_bytes)
                if len(head) < 65536:
                    head += piece[:65536 - len(head)]
                fh.write(piece)
                held.update(announced - written)
                if written % every < len(piece) and not _att.disk_allows(inbox, 0):
                    return _refuse(507, "disk_full")
        if request.state.source == "chat":
            sniffed = _att.sniff(head, request.state.filename)
            if sniffed is None:
                return _refuse(415, "type")
            kind, mime = sniffed
        complete = True
    except ClientDisconnect:
        return _refuse(499, "cancelled")
    finally:
        held.release()
        if not complete:
            tmp.unlink(missing_ok=True)         # a refused or cancelled upload leaves nothing behind
    if request.state.source != "chat":
        # to_thread (2026-07-19 P1-4 audit): registering computes the summary embedding SYNCHRONOUSLY.
        ref = await asyncio.to_thread(memapi.adopt_episode, tmp, filename=request.state.filename,
                                      mime=None)
        return {"name": ref["name"], "size": ref["bytes"], "episode_id": ref["episode_id"]}
    return await _keep_chat_file(tmp, request.state.filename, kind, mime)


async def _keep_chat_file(tmp: Path, name: str, kind: str, mime: str) -> dict:
    """Read (bounded, off the event loop, with a clock), keep, and attach. The file is stored even when the
    reading fails — the turn is then told it could not be read, and why."""
    lim = _att.limits()
    thumb_tmp = tmp.with_suffix(".thumb.jpg")

    abandoned = threading.Event()

    def _work():
        out = _att.process(tmp, kind, thumb_tmp)
        # A thread cannot be stopped: one that outlived its clock removes what it wrote itself, when it ends.
        if abandoned.is_set():
            thumb_tmp.unlink(missing_ok=True)
        return out

    try:
        reading, why, has_thumb = await asyncio.wait_for(asyncio.to_thread(_work),
                                                         timeout=float(lim["process_timeout_s"]))
    except asyncio.TimeoutError:
        abandoned.set()
        thumb_tmp.unlink(missing_ok=True)
        reading, why, has_thumb = "", "reading took too long", False
    ref = await asyncio.to_thread(memapi.adopt_episode, tmp, filename=name, mime=mime,
                                  summary=_att.summary_of(name, kind, reading))
    eid = int(ref["episode_id"])
    _att.save_reading(eid, reading)
    if has_thumb and thumb_tmp.exists():
        os.replace(thumb_tmp, _att.thumb_path(eid))
    _att.attach({"episode_id": eid, "name": ref["name"], "kind": kind, "mime": mime, "bytes": ref["bytes"],
                 "why_not": why})
    return {"ok": True, "name": ref["name"], "size": ref["bytes"], "episode_id": eid, "kind": kind, "mime": mime,
            "thumb": f"/api/files/{eid}/thumb" if has_thumb else None, "read": bool(reading)}


@router.get("/api/files/limits")
async def file_limits():
    """The chat composer's limits — the same declared numbers the door enforces (`config/attachments.default.json`)."""
    return _att.public_limits()


@router.delete("/api/files/attached/{episode_id}")
async def detach(episode_id: int):
    """He removed an attachment chip before sending: the turn stops seeing it (the file stays stored)."""
    return {"ok": True, "detached": _att.detach(episode_id)}


@router.get("/api/files/{episode_id}/thumb")
async def thumb(episode_id: int):
    p = _att.thumb_path(episode_id)
    if not p.is_file():
        raise HTTPException(404, "no thumbnail")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/files")
async def list_files():
    eps = memapi.list_episodes()
    return {"files": [{"name": e["name"], "size": e.get("bytes"), "mime": e.get("mime"),
                       "summary": e.get("summary"), "episode_id": e["id"]} for e in eps]}


@router.post("/api/memory/recall")
async def memory_recall(query: str = Body("", embed=True), k: int = Body(8, embed=True),
                        source: str = Body("all", embed=True), kind: str = Body("", embed=True),
                        hours: float = Body(0, embed=True)):
    """MEMORY bridge for the SlowBrain Claude Code agents (V2-036): direct READ (no LLM, milliseconds) of the
    memories relevant to `query`. It is the "ask for a fact" half of the serial component: the agent makes one call,
    receives the nuggets, and continues execution. Read-only (it does not change weights here beyond the query's
    normal reinforcement).

    WITH PROVENANCE (V2-802 T-06): every row carries `id`, `created` (local ISO), `level`, `kind`, `slot`,
    `source`/`entity` and its `lane`, and the digest prints them, so a worker can tell an inbound email from a fact
    the operator dictated and can cite where «it is on record». Three lanes, in this order, never fused:
    `memory` (his facts, pills, errand results), `conversation` (what was said, verbatim, with session and who —
    V2-803 T-01) and `messages` (what others wrote him). `source` filters to one lane, or to one writer's
    `meta.source` (`whatsapp`, `email`, `voice`…); `kind` to a comma list of kinds. `source="conversation"` with an
    empty query reads the last `hours` (default 48) of conversation whole."""
    q = (query or "").strip()
    src = (source or "all").strip().lower() or "all"
    if not q and src != "conversation":
        return {"memories": [], "text": ""}
    try:
        # to_thread (2026-07-19 P1-4 audit): query = embedding + retriever + reranker (hundreds of ms) —
        # outside the server's event loop, as FlashBrain already does (V2-011).
        return await asyncio.to_thread(_recall_sync, q, max(1, min(int(k or 8), 20)), src, kind or "",
                                       float(hours or 0))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"recall falló: {e}")


def _worker_source(task_id: str, token: str) -> str | None:
    """Per-task auth for the write bridge (2026-07-14 audit): same scheme as `/api/worker/act` —
    the worker sends its `ZAELAR_TASK_ID`/`ZAELAR_TASK_TOKEN` (headers, set by `mem_cli`), and they are verified
    against the dispatch RAM registry. Returns the provenance label, or None if authorization fails.
    `ZAELAR_MEM_API_OPEN=1` = hatch for local dev/scripts (`source="local"` is stamped)."""
    if task_id and token:
        try:
            from nucleo import dispatch
            rec = dispatch.get_record(task_id)
            if rec is not None and dispatch.rec_token(rec) == token:
                return f"worker:{task_id}"
        except Exception:
            return None
        return None
    if os.getenv("ZAELAR_MEM_API_OPEN", "").strip() == "1":
        return "local"
    return None


@router.post("/api/memory/remember")
async def memory_remember(text: str = Body(..., embed=True), slot: str = Body("", embed=True),
                          kind: str = Body("", embed=True), importance: float = Body(None, embed=True),
                          x_zaelar_task: str = Header("", alias="X-Zaelar-Task"),
                          x_zaelar_token: str = Header("", alias="X-Zaelar-Token")):
    """MEMORY bridge for Brain Workers (V2-036/V2-038): WRITING through the ONE authorized writer
    (async queue), preserving the single-writer invariant. Hardened in the 2026-07-14 audit:
    it requires the worker's PER-TASK token (headers from `mem_cli`) and goes through
    `memory_agent.remember_external` — the same precision gates as voice, with no access to `state` or identity slots."""
    t = (text or "").strip()
    if not t:
        raise HTTPException(400, "text vacío")
    source = _worker_source(x_zaelar_task.strip(), x_zaelar_token.strip())
    if source is None:
        raise HTTPException(401, "token de tarea inválido o ausente (ZAELAR_TASK_ID/ZAELAR_TASK_TOKEN)")
    item = {"text": t}
    if slot:
        item["slot"] = slot
    if kind:
        item["kind"] = kind
    if importance is not None:
        item["importance"] = float(importance)
    try:
        from nucleo import memory_agent
        res = await memory_agent.remember_external(item, source=source)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"remember falló: {e}")
    if not res.get("ok"):
        raise HTTPException(422, f"descartado por el gate de precisión ({res.get('reason')})")
    return res


@router.get("/api/memory/map")
async def memory_map():
    """COMPLETE map of memory for the VIEWER (V2-014 · T129): state + memories by layer (short/long) +
    graph (`edges`) + complete metadata (scoring, weight, access, recency, ttl, pinned, dates). Read-only,
    `no-cache` — the viewer rereads it on the fly when the `memory.updated` signal arrives via SSE (real time)."""
    return JSONResponse(await asyncio.to_thread(memapi.map), headers={"Cache-Control": "no-cache"})
