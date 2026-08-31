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
import os

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from memory import api as memapi

router = APIRouter()

_MAX_BYTES = 50 * 1024 * 1024   # 50 MB — ample for screenshots/PDFs, an inexpensive safeguard against filling the disk


@router.post("/api/files/upload")
async def upload(file: UploadFile = File(...), source: str = Form("drop")):
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "archivo demasiado grande")
    # to_thread (2026-07-19 P1-4 audit): write_episode computes the summary embedding SYNCHRONOUSLY
    # (HTTP to Ollama, 20s timeout) — never in uvicorn's event loop (SSE/queue/widgets run there).
    ref = await asyncio.to_thread(
        memapi.write_episode, data, filename=file.filename or "archivo", mime=file.content_type or None,
    )
    return {"name": ref["name"], "size": ref["bytes"], "episode_id": ref["episode_id"]}


@router.get("/api/files")
async def list_files():
    eps = memapi.list_episodes()
    return {"files": [{"name": e["name"], "size": e.get("bytes"), "mime": e.get("mime"),
                       "summary": e.get("summary"), "episode_id": e["id"]} for e in eps]}


@router.post("/api/memory/recall")
async def memory_recall(query: str = Body(..., embed=True), k: int = Body(8, embed=True)):
    """MEMORY bridge for the SlowBrain Claude Code agents (V2-036): direct READ (no LLM, milliseconds) of the
    memories relevant to `query`. It is the "ask for a fact" half of the serial component: the agent makes one call,
    receives the nuggets, and continues execution. Read-only (it does not change weights here beyond the query's
    normal reinforcement)."""
    q = (query or "").strip()
    if not q:
        return {"memories": [], "text": ""}
    try:
        # to_thread (2026-07-19 P1-4 audit): query = embedding + retriever + reranker (hundreds of ms) —
        # outside the server's event loop, as FlashBrain already does (V2-011).
        res = await asyncio.to_thread(memapi.query, q, limit=max(1, min(int(k or 8), 20)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"recall falló: {e}")
    # `slot` is a COLUMN of the row the retriever returns (since 2026-08-21), not a key of `meta` — and `meta`
    # is not among the columns it selects, so the old read reported an empty slot for EVERY pill. A worker
    # asking memory what it knows was told nothing about which of those facts were singular.
    mems = [{"text": m.get("text", ""), "kind": m.get("kind", ""), "slot": m.get("slot") or ""}
            for m in (res.get("memories") or []) if m.get("text")]
    digest = "\n".join(f"- {m['text']}" for m in mems) or "(sin recuerdos relevantes)"
    return {"memories": mems, "text": digest}


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
