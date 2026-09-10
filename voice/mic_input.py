#
# mic_input.py — THE microphone switch (V2-654).
#
# ONE fact, held server-side: is the operator's microphone input muted? Everything that ACTS on what the
# microphone heard asks HERE, and nothing else decides it.
#
# WHY THIS EXISTS (measured 2026-09-10, session 85eec898). The mute lived only in the browser, spread across
# SIX writers, and four of them (`main.js` boot, the ⏻ power button on both shells, `DockBar`) wrote the icon's
# signal + localStorage and NEVER touched the audio: `applyMic()` was not on their path. So the 🎤 icon showed
# CLOSED while the track kept publishing, the engine transcribed the operator for seven minutes, escalated an
# errand off what it heard — and nothing anywhere could notice, because the engine had no notion of a microphone
# switch at all. The operator's verdict, verbatim: «cuando yo desactivo el icono, ese estado es total … el estado
# se debe controlar en un solo sitio y controla todo el sistema. No puede fallar nunca.»
#
# The client half (`frontend/app/services/mic.js`) is the single DOOR that writes; this module is the single
# HOLDER that the rest of the engine reads. They are kept in step by the heartbeat (~4s), so a divergence in
# either direction self-corrects without anyone having to remember to re-assert.
#
# DIRECTION OF FAILURE — deliberate and asymmetric:
#   • muted is STICKY: once told, it stays until explicitly lifted. A client that mutes and then dies (crash,
#     tab killed, network gone) leaves the engine muted, which is the safe side of the accident.
#   • the boot default is OPEN, because at boot no microphone has been captured yet and a stale/absent client
#     must never be able to leave the agent deaf forever — deafness is the OTHER failure the same session paid
#     for (16 turns discarded in a row while the operator asked what was wrong).
#
# NOT a privacy boundary against the browser: if the published track really is live, audio still reaches STT and
# the transcript still appears in observability. That is on purpose — the transcript is the EVIDENCE that a
# divergence happened, and hiding it is what made this cost seven minutes to see. What the switch guarantees is
# that no muted audio ever reaches the BRAIN: no model, no tool, no widget, no memory, no errand.
#
from __future__ import annotations

import threading
import time

_mx = threading.Lock()
_state = {"muted": False, "at": 0.0, "source": ""}


def is_muted() -> bool:
    """The one answer. Cheap enough for the hot path of every turn."""
    with _mx:
        return bool(_state["muted"])


def snapshot() -> dict:
    """The whole fact, for the API and the viewer — `muted`, when it last changed, and who said so."""
    with _mx:
        return {"muted": bool(_state["muted"]), "at": _state["at"], "source": _state["source"]}


def set_muted(muted: bool, *, source: str = "frontend", now: float | None = None) -> dict:
    """Write the fact. Idempotent BY DESIGN: the heartbeat re-asserts the same value every ~4s, so only a real
    CHANGE is worth an event — otherwise the timeline would carry 15 rows a minute saying nothing happened."""
    muted = bool(muted)
    now = time.time() if now is None else now
    with _mx:
        changed = muted != bool(_state["muted"])
        _state["muted"], _state["at"], _state["source"] = muted, now, (source or "")[:40]
    if changed:
        _emit(muted, source)
    return {"ok": True, "muted": muted, "changed": changed}


def reset() -> None:
    """Back to the boot default (open). For tests and for a full engine reset — NOT a way to lift a mute."""
    with _mx:
        _state.update(muted=False, at=0.0, source="")


def _emit(muted: bool, source: str) -> None:
    """Observability, never fatal: this module is called from the turn's hot path and from a route handler, and
    neither may die because the observer is unavailable."""
    try:
        from voice.observer import emit
        emit("mic", "🎤⃠ micrófono CERRADO" if muted else "🎤 micrófono abierto",
             role="system", extra={"muted": muted, "src": source})
    except Exception:  # noqa: BLE001
        pass
