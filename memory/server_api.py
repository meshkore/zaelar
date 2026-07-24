#
# memory/server_api.py — HTTP para la memoria episódica (V2-003 · T54). Reemplaza a files/server_api.py: el
# operador pega una imagen o arrastra un fichero al frontend (frontend/app/main.js) y aterriza aquí. En vez de
# la vieja bandeja plana files/uploads/ + una nota [SISTEMA] con la ruta (que era para las tools de fichero de
# Hermes), ahora el binario va a la memoria EPISÓDICA (bytes en el data-dir, resumen buscable embebido) →
# el retriever del cerebro lo encuentra por su cuenta, sin ruta absoluta ni tools de Hermes. Sin auth: mismo
# modelo de confianza que el resto de la API local.
#
import asyncio
import os

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from . import api as memapi

router = APIRouter()

_MAX_BYTES = 50 * 1024 * 1024   # 50 MB — holgado para capturas/PDFs, guarda barata contra llenar el disco


@router.post("/api/files/upload")
async def upload(file: UploadFile = File(...), source: str = Form("drop")):
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "archivo demasiado grande")
    # to_thread (auditoría 2026-07-19 P1-4): write_episode calcula el embedding del resumen SÍNCRONO
    # (HTTP a Ollama, timeout 20s) — jamás en el event loop de uvicorn (SSE/cola/widgets viven ahí).
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
    """Puente de MEMORIA para los agentes Claude Code del SlowBrain (V2-036): LECTURA directa (sin LLM, ms) de los
    recuerdos relevantes a `query`. Es la mitad "pide un dato" de la pieza serial: el agente hace una llamada,
    recibe las píldoras y sigue su ejecución. Read-only (no muta pesos aquí más que el refuerzo normal del query)."""
    q = (query or "").strip()
    if not q:
        return {"memories": [], "text": ""}
    try:
        # to_thread (auditoría 2026-07-19 P1-4): query = embedding + retriever + reranker (cientos de ms) —
        # fuera del event loop del server, como ya hace el FlashBrain (V2-011).
        res = await asyncio.to_thread(memapi.query, q, limit=max(1, min(int(k or 8), 20)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"recall falló: {e}")
    mems = [{"text": m.get("text", ""), "kind": m.get("kind", ""), "slot": (m.get("meta") or {}).get("slot", "")}
            for m in (res.get("memories") or []) if m.get("text")]
    digest = "\n".join(f"- {m['text']}" for m in mems) or "(sin recuerdos relevantes)"
    return {"memories": mems, "text": digest}


def _worker_source(task_id: str, token: str) -> str | None:
    """Auth por-tarea del puente de escritura (auditoría 2026-07-14): mismo esquema que `/api/worker/act` —
    el worker manda su `ZAELAR_TASK_ID`/`ZAELAR_TASK_TOKEN` (headers, los pone `mem_cli`) y se verifica contra
    el registro RAM de dispatch. Devuelve la etiqueta de procedencia, o None si no autoriza.
    `ZAELAR_MEM_API_OPEN=1` = escotilla para dev/scripts locales (queda estampado `source="local"`)."""
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
    """Puente de MEMORIA para los Brain Workers (V2-036/V2-038): ESCRITURA por el ÚNICO escritor sancionado
    (cola async), preservando el invariante de escritor único. Endurecido en la auditoría 2026-07-14:
    exige el token POR-TAREA del worker (headers de `mem_cli`) y entra por `memory_agent.remember_external`
    — mismos gates de precisión que la voz, sin acceso a `state` ni a los slots de identidad."""
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
    """Mapa COMPLETO de la memoria para el VISOR (V2-014 · T129): estado + recuerdos por capa (corto/largo) +
    grafo (`edges`) + metadatos completos (scoring, weight, access, recencia, ttl, pinned, fechas). Read-only,
    `no-cache` — el visor lo re-lee al vuelo cuando llega la señal `memory.updated` por SSE (tiempo real)."""
    return JSONResponse(await asyncio.to_thread(memapi.map), headers={"Cache-Control": "no-cache"})
