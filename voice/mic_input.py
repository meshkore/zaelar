# mic_input.py — THE microphone switch (V2-654) and THE input door to the STT (V2-831 T-18).
#
# ONE server-side fact — is his microphone muted? — that everything acting on what it heard asks (session 85eec898:
# the icon moved, the audio did not, and he was transcribed for seven minutes). `frontend/app/services/mic.js`
# writes it, the ~4 s heartbeat re-asserts it. Muted is STICKY (the safe side of a dead client); boot is OPEN
# (a stale client must never leave the agent deaf). NOT the attention mode: it is his own hand — consulted first,
# never lifted by a wake word, and lifting it changes no attention state.
#
# THE INPUT DOOR: a cloud STT bills every frame it is PUSHED (Deepgram: one report per 5 s), so closed states
# used to cost what an open mic did (12 usage reports a minute for silence). The one rule,
#     feeds_stt() = not muted  and  not parked  and  not stopped (⏻),
# is re-applied on every write to the session's audio INPUT, whose room input then drops frames before VAD and
# STT. A future closed state joins the conjunction, never a gate elsewhere; `blocks_turn` stays as the backstop;
# `parked` (the wake-word mode's TRANSPORT fact, `wakeword.js`) is never persisted and resets with each session.
from __future__ import annotations

import threading
import time

_mx = threading.Lock()
_state = {"muted": False, "at": 0.0, "source": ""}
_tap = {"parked": False}
_input = {"sink": None, "applied": None}   # the live session's `(enabled) -> None`; one voice holder at a time


def is_muted() -> bool:
    """The one answer. Cheap enough for the hot path of every turn."""
    with _mx:
        return bool(_state["muted"])


def snapshot() -> dict:
    """The whole fact, for the API and the viewer — `muted`, when it last changed, and who said so."""
    with _mx:
        return {"muted": bool(_state["muted"]), "at": _state["at"], "source": _state["source"]}


def set_muted(muted: bool, *, source: str = "frontend", now: float | None = None, dev: str = "") -> dict:
    """Write the fact. Idempotent BY DESIGN: the heartbeat re-asserts the same value every ~4s, so only a real
    CHANGE is worth an event — otherwise the timeline would carry 15 rows a minute saying nothing happened."""
    muted = bool(muted)
    now = time.time() if now is None else now
    with _mx:
        changed = muted != bool(_state["muted"])
        _state["muted"], _state["at"], _state["source"] = muted, now, (source or "")[:40]
    if changed:
        _say("🎤⃠ micrófono CERRADO" if muted else "🎤 micrófono abierto",
             extra={"muted": muted, "src": source, **({"dev": dev} if dev else {})})
    apply_input()
    return {"ok": True, "muted": muted, "changed": changed}


def set_parked(parked: bool) -> None:
    """The browser parked (or unparked) its track for the wake word; applied at once, so the unpark of a spotted
    name opens the STT before the sentence behind it arrives."""
    with _mx:
        _tap["parked"] = bool(parked)
    apply_input()


def feeds_stt() -> bool:
    """THE input rule: may audio reach the speech recogniser right now? Every closed state answers no."""
    with _mx:
        if _state["muted"] or _tap["parked"]:
            return False
    from nucleo import runstate
    return not runstate.stopped()


def use_input(sink) -> None:
    """The voice session installs its input setter. It APPLIES at once (a session born with the mic closed feeds
    not one frame) and starts unparked."""
    with _mx:
        _input["sink"], _input["applied"], _tap["parked"] = sink, None, False
    apply_input()


def clear_input(sink) -> None:
    """Only OUR sink: when the voice moves, the next session registers before this one closes."""
    with _mx:
        if _input["sink"] is sink:
            _input["sink"], _input["applied"] = None, None


def apply_input() -> bool | None:
    """Push `feeds_stt()` into the live input — only on a CHANGE, so the ~4 s beat never flaps the lever (and the
    beat is what carries a ⏻ stop made elsewhere to the input). Returns what is applied; None = no session."""
    with _mx:
        sink, applied = _input["sink"], _input["applied"]
    if sink is None:
        return None
    want = feeds_stt()
    if applied is want:
        return want
    with _mx:
        _input["applied"] = want
    try:
        sink(want)
    except Exception as e:  # noqa: BLE001 — never fatal on the hot path; forgetting it makes the next beat retry
        with _mx:
            _input["applied"] = None
        _say("⚠️ audio input lever failed", extra={"stt_input": want, "error": str(e)[:160]})
        return None
    _say("👂 audio input OPEN (STT)" if want else "👂⃠ audio input CLOSED (no STT)", extra={"stt_input": want})
    return want


def blocks_turn(text: str) -> bool:
    """The BACKSTOP: does the switch swallow this turn? True = no model, tool, widget, memory or errand. Asked
    BEFORE the attention gate (closed is not an opinion about who was addressed). The typed turn is the one
    exemption, consumed one-shot (`attention.consume_typed`) — the mic is closed IN ORDER to type. Firing at all
    means audio reached the STT with the switch closed, so the event carries the TEXT: it is the evidence."""
    from voice import attention
    if attention.consume_typed() or not is_muted():
        return False
    _say("🎤⃠ turno DESCARTADO — el micrófono está cerrado", text=(text or "")[:200], role="user",
         extra={"muted": True, "src": snapshot().get("source") or ""})
    return True


def reset() -> None:
    """Back to the boot default (open). For tests and for a full engine reset — NOT a way to lift a mute."""
    with _mx:
        _state.update(muted=False, at=0.0, source="")
        _tap["parked"] = False
        _input.update(sink=None, applied=None)


def _say(label: str, *, role: str = "system", **kw) -> None:
    """Observability, never fatal: called from the turn's hot path and from route handlers."""
    try:
        from voice.observer import emit
        emit("mic", label, role=role, **kw)
    except Exception:  # noqa: BLE001
        pass
