"""nucleo/flash/probe_api.py — HTTP surface of the FlashBrain probe channel (V2-098 split).

Extracted from nucleo/flash/probe.py: a thin FastAPI wrapper around `run_turn`/`_session`/`_SESSIONS`, which stay
in probe.py (the core the voice provider mirrors). probe.py re-exports `router` so the one mount point
(`server/__init__.py`: `from nucleo.flash.probe import router as flash_probe_router`) keeps working unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Body

from nucleo.flash.probe import _session, _SESSIONS, run_turn

router = APIRouter()


def _wall(role: str, text: str) -> None:
    """Put one line of THIS conversation on the operator's chat wall, live.

    Operator's rule (2026-08-28), watching an unattended round drive the agent while the chat stayed empty:
    «si se opera por voz se transcribe al chat, y si se opera por chat se ve el texto, tanto si se hace
    manualmente sobre el widget del chat como si estamos manejando la conversación a través de la API». One
    conversation, one place to read it, whatever door it came in through.

    It was missing because this channel was built as a HEADLESS test surface (V2-032): nobody was meant to be
    looking. That stopped being true the day the lab agents got a fixed port so the operator could watch a
    round happen — and an agent working silently is indistinguishable from an agent stuck.

    `wall` in the extra is the marker the frontend keys on (`services/sse.js`), NOT the label: a substring
    match on a label is a contract nobody can see from either side. It rides on `kind="brain"` because that
    is already a family the wall subscribes to, so this adds a reader, not a taxonomy (the observability
    families are total and enforced by `test_observer_categories.py`).

    Deliberately NOT emitted as `kind="transcript"`, which is the other event the wall paints: that one also
    feeds the frontend's voice-command fast path (`handleWidgetVoice`), so a probe turn that says "cierra la
    agenda" would be executed TWICE — once by the channel that already executes actions, once by the browser.
    Showing a conversation must never change what it does.

    Never fatal: the wall is a window onto the turn, not part of it.
    """
    if not (text or "").strip():
        return
    try:
        from voice.observer import emit
        emit("brain", "💬 chat (canal de texto)", text=text[:4000],
             role="user" if role == "user" else "assistant",
             extra={"cat": "flash", "wall": "you" if role == "user" else "agent"})
    except Exception:  # noqa: BLE001
        pass


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
    # AL MURO, antes de nada: el turno puede tardar segundos y el operador tiene que ver ya lo que se ha
    # pedido. Si se pintara al final, la pantalla estaría muda justo mientras el agente trabaja — que es el
    # rato en el que se mira.
    _wall("user", text)
    res = await run_turn(text, sid=session, ingest=ingest, model=model, execute=execute)
    # `reply` es una LISTA de frases (el turno puede decir varias). Unirlas y no `str()`-earlas: un `str()`
    # sobre la lista pintaría en el muro `['Te las busco ahora mismo.']`, corchetes y comillas incluidos.
    _reply = res.get("reply")
    _wall("agent", " ".join(str(x) for x in _reply) if isinstance(_reply, list) else str(_reply or ""))
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
