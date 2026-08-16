"""nucleo/flash/probe_api.py — HTTP surface of the FlashBrain probe channel (V2-098 split).

Extracted from nucleo/flash/probe.py: a thin FastAPI wrapper around `run_turn`/`_session`/`_SESSIONS`, which stay
in probe.py (the core the voice provider mirrors). probe.py re-exports `router` so the one mount point
(`server/__init__.py`: `from nucleo.flash.probe import router as flash_probe_router`) keeps working unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Body

from nucleo.flash.probe import _session, _SESSIONS, run_turn

router = APIRouter()


@router.post("/api/flash/say")
async def say(text: str = Body(..., embed=True), session: str = Body("default", embed=True),
              ingest: bool = Body(True, embed=True), prompt: bool = Body(False, embed=True),
              model: str = Body("", embed=True), execute: bool = Body(False, embed=True)) -> dict:
    """Inyecta un turno de texto al FlashBrain y devuelve su respuesta + acción + latencias (canal de prueba).
    `model` (opcional) fuerza otro modelo rápido para A/B. `execute` (V2-049) EJECUTA de verdad las acciones de
    worker (escalada/inyección/respuesta/stop) → test e2e de gestiones web por texto, sin voz."""
    res = await run_turn(text, sid=session, ingest=ingest, model=model, execute=execute)
    if prompt and res.get("ok"):
        # opcional: incluye el prompt compuesto (para inspeccionar qué estado/memoria vio el modelo)
        from nucleo.flash.prompt import build_flash_system, needs_recall
        sys_txt, _ = build_flash_system(directive=_session(session).directive,
                                        recall_query=text if needs_recall(text) else "", turn_text=text)
        res["prompt"] = sys_txt
    return res


@router.post("/api/flash/reset")
async def reset(session: str = Body("default", embed=True)) -> dict:
    """Limpia la ventana conversacional del probe (NO toca la memoria; para eso, `make reset`)."""
    # A reset is an explicit causal barrier in headless tests: all completed memory writes must be visible in the
    # first turn of the new window. It does not run on the physical voice hot path.
    from nucleo.flash import memory_cache
    await memory_cache.refresh()
    _SESSIONS.pop(session or "default", None)
    return {"ok": True, "session": session or "default"}
