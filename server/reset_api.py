"""The three resets — light, hard and the dialog with checkboxes — and WHO asked for them (from
`server/voice_api.py`, refactor2710-13 T-03). Mounted through `voice_api.router`."""
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from voice.observer import clear_log, emit, rotate_session

from . import state as S

router = APIRouter()


def _who_asked(request: "Request | None") -> dict:
    """WHO asked for this reset — an attribution fact, kept with the event that destroys work.

    A hard reset kills live workers, cancels escalations and blanks the canvas, and the RESET event recorded
    everything about that EXCEPT who ordered it. Measured 2026-09-03 on the operator's own engine: a reset
    fired mid-errand with no `topbar:reset`, no `orb:power` and no `run/stop` in front of it — so it did not
    come from the button — and there was no way to say what did. The engine then apologised to the operator
    for closing widgets it had not chosen to close, because nothing in the prompt or the log could name the
    author. An event that records what was destroyed and not who ordered it cannot answer the only question
    asked afterwards.

    Deliberately coarse: client host and a bounded User-Agent. Enough to tell the desktop frontend from an
    automated caller (a harness sends a fixed short UA; a real browser's carries its version), and nothing
    that would turn an event log into a tracking record.
    """
    if request is None:
        return {"host": "", "ua": ""}
    try:
        return {"host": str(getattr(getattr(request, "client", None), "host", "") or ""),
                "ua": str(request.headers.get("user-agent") or "")[:120]}
    except Exception:  # noqa: BLE001 — attribution must never be the reason a reset fails
        return {"host": "", "ua": ""}


@router.post("/reset")
async def reset():
    # LIGHT reset (also used by reconnect): clears session + log. Does NOT kill background work or write memory.
    S.reset_session_state()
    clear_log()
    return JSONResponse(emit("session", "RESET"))


def _live_reset() -> tuple[dict, dict]:
    """The sequence every hard reset shares, live: freeze and kill the work (`nucleo/reset.py`), a NEW session (new id
    + observability reset, not just a clean log), and close ALL canvas cards (frontend: desktop.closeAll())."""
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")
    from nucleo.acts import canvas
    canvas.apply("close", src="system:reset", emit=emit)        # a reset empties the canvas
    return summary, ses


@router.post("/reset/hard")
async def reset_hard(request: Request = None):
    """Deliberate HARD RESET (frontend «Reset» button, after confirmation). Careful sequence: FREEZE in-flight work
    in STATE memory, leave the order RECORD in short-term memory, KILL background processes, then clear the canvas
    (close all widgets) + session + log. See `nucleo/reset.py`."""
    summary, ses = _live_reset()
    return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "by": _who_asked(request),
                                                        "session": ses.get("session_id", "")}))


@router.post("/api/reset/full")
async def reset_full(payload: dict | None = None, request: Request = None):
    """Reset dialog with CHECKBOXES (V2-063, operator request 2026-07-23): besides the ALWAYS base (observability +
    blank desktop, same as /reset/hard), it can optionally delete `wipe_memory` (state/short/long term — one
    "Memory" button) and/or `wipe_credentials` (WhatsApp/Telegram/browser/search). Deleting memory/credentials
    requires the process to die (SQLite in use, browser profiles open) → if EITHER is requested, an AUTOMATIC
    restart is launched in the background (`scripts/reset-memory.sh` + `make run`, detached) and `restarting:true`
    is returned BEFORE the server dies, so the frontend can show "restarting…" and reconnect only when it comes
    back. If neither is requested, it is EXACTLY `/reset/hard` (live, no restart)."""
    p = payload or {}
    wipe_memory = bool(p.get("wipe_memory"))
    wipe_credentials = bool(p.get("wipe_credentials"))
    # V2-670, the operator's «quiero inicializar un agente nuevo en otro idioma, todo de cero»:
    # `wipe_profile` is what actually makes the first-run LANGUAGE CEREMONY fire again (it empties
    # `stt_language`, the gate `i18n.init.detect.should_detect()` reads), and `wipe_files` deletes the
    # agent's own library. Both need the process dead for the same reason the other two do.
    wipe_profile = bool(p.get("wipe_profile"))
    wipe_files = bool(p.get("wipe_files"))

    # ALWAYS base (observability + desktop): same sequence as /reset/hard, live, no restart.
    summary, ses = _live_reset()

    if not wipe_memory and not wipe_credentials and not wipe_profile and not wipe_files:
        return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "restarting": False,
                                                            "by": _who_asked(request),
                                                            "session": ses.get("session_id", "")}))

    # Memory and/or credentials: AUTOMATIC restart in a DETACHED process (survives this process dying).
    # `reset-memory.sh` stops the server itself (finds the PID by port), deletes, and bumps desktop-epoch; then we
    # relaunch with a normal `make run`, logging to a file (same pattern as manual restarts).
    import subprocess
    import time as _time
    engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ts = _time.strftime("%Y%m%d-%H%M%S")
    flags = (("" if wipe_memory else " --keep-memory") + (" --wipe-credentials" if wipe_credentials else "")
             + (" --factory" if wipe_profile else "") + (" --wipe-files" if wipe_files else ""))
    cmd = (
        f"sleep 1; bash scripts/reset-memory.sh --yes{flags}; "
        f"nohup make run > .meshkore/logs/run-{ts}.log 2>&1 &"
    )
    try:
        subprocess.Popen(["bash", "-c", cmd], cwd=engine_dir, start_new_session=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_full: no se pudo lanzar el reinicio: {e}")
        return JSONResponse({"ok": False, "error": "restart_spawn_failed"}, status_code=500)
    return JSONResponse({"ok": True, "restarting": True, "wipe_memory": wipe_memory,
                         "wipe_credentials": wipe_credentials, "wipe_profile": wipe_profile,
                         "wipe_files": wipe_files, "reset": summary})
