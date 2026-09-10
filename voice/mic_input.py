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
# NOT THE ATTENTION MODE, and the two may never be written in terms of each other (operator, 2026-09-10).
# The 🤖 wake-word mode is how a permanently OPEN microphone is made livable: audio keeps arriving, it keeps
# being transcribed, and `voice/attention.py` decides turn by turn what was addressed to us — a wake word or
# an open conversation window effectively switches the agent's ear on and off by VOICE, and that is
# necessary, not a workaround. Nothing here changes any of it: those rules stay exactly as they were.
#
# THIS switch is the other axis — the operator's own hand shutting the input. Hence the order and the
# asymmetry: a hard close is consulted FIRST and no wake word can lift it (he did not authorise us to hear
# him at all), while lifting the close changes no attention state whatsoever — the mode he had is the mode he
# gets back. And a turn this switch swallows never reaches `note_directed()`, so it cannot open or refresh a
# conversation window on its way out.
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


def blocks_turn(text: str) -> bool:
    """THE rule: does the switch swallow this turn? True = it does not exist — no model, no tool, no widget,
    no memory, no errand.

    It is consulted BEFORE the attention gate on purpose: «closed» is not an opinion about who was being
    addressed, it is that we were not authorised to hear him, so no conversation window and no wake word may
    lift it.

    The TYPED turn is the only exemption, and it is exactly the use case — the microphone is closed IN ORDER
    to type. Consumed one-shot (`attention.consume_typed`, no time window): with a window, typing and then
    speaking would walk the spoken turn straight through the closed switch.

    That this ever fires MEANS the browser kept publishing audio with the icon shut — the 2026-09-10 failure
    (session 85eec898), where four of the state's six writers moved the icon and not the track. Which is why
    the event carries the TEXT: it is the evidence of the divergence, and without it that cost seven minutes
    to see."""
    from voice import attention
    if attention.consume_typed():
        return False
    if not is_muted():
        return False
    try:
        from voice.observer import emit
        emit("mic", "🎤⃠ turno DESCARTADO — el micrófono está cerrado", text=(text or "")[:200], role="user",
             extra={"muted": True, "src": snapshot().get("source") or ""})
    except Exception:  # noqa: BLE001
        pass
    return True


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
