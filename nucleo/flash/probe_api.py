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
    # FIRST-RUN LANGUAGE, on a channel that has no way to ASK (V2-170). The voice pipeline opens a brand-new
    # install with a blocking "what language should I use?" turn and locks the answer; a text channel gets no
    # such turn, so without this it stays on the product default (English) for as long as it lives. That is not
    # only how the reply reads: `nucleo/flash/site_catalog.py` resolves its LOCALE from the same code, so a
    # Spanish errand was being handed opentable.com and ticketmaster.com instead of thefork.es and entradas.es.
    #
    # It lives HERE, at the HTTP edge, and not inside `run_turn`: that function is also how the suite drives a
    # turn IN-PROCESS, and a detector that persists a language from there flips `ZAELAR_LANGUAGE` for every test
    # that runs after it (measured — `test_suite_isolation.py` caught exactly that). The edge is the honest
    # layer anyway: it is where there is a real operator on the other side.
    #
    # NOT mirrored into the voice provider on purpose: a silent lock there would race the modal's question and
    # could commit the wrong language before it is answered. A no-op once a language is chosen; never raises.
    try:
        from i18n.init import detect as _lang_detect
        _lang_detect.ensure_for_text(text)
    except Exception:
        pass
    res = await run_turn(text, sid=session, ingest=ingest, model=model, execute=execute)
    if prompt and res.get("ok"):
        # opcional: incluye el prompt compuesto (para inspeccionar qué estado/memoria vio el modelo)
        # Misma guarda que el turno: esto corre en el loop del server, así que un recall lento aquí congela el
        # motor igual — y encima por una opción de INSPECCIÓN, que es el peor sitio donde perder el proceso.
        from nucleo.flash.prompt import build_flash_system, needs_recall
        from nucleo.turn import recall_budget as _recall
        _rb, _ = await _recall.compose(text if needs_recall(text) else "")
        sys_txt, _ = build_flash_system(directive=_session(session).directive,
                                        recall_block=_rb, turn_text=text)
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
