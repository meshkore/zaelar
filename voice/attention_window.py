"""voice/attention_window.py — how long the wake-word window stays open after zaelar's last word.

Operator directive (2026-09-09): a flat 12s was wrong in both directions — after «dime el tiempo» → «Hecho.»
four seconds of open mic is plenty, while mid-errand (a worker searching for him, a question just asked, a
conversation flowing) fifteen is the natural pause. DETERMINISTIC and model-free on purpose: the verdict rides
every reply, a model call here would add latency and a coin-flip to each one, and all four signals are cheap
process-level facts. `attention.note_reply()` is the only caller; `attention.window_s()` reads the result.

The scale (operator's own bracket at birth: «entre 4 y 15 segundos»):
  15s  the reply ASKS something (an answer is expected), or a worker is LIVE for him (check-ins are natural)
  12s  a conversation is flowing (several directed turns in the last 90s)
   5s  a short bare ack with no dialogue behind it — the «dime el tiempo» → «Hecho.» shape
   8s  anything else

⚠️ CAPPED AT 5s SINCE 2026-09-10 (operator directive, superseding the bracket above for the ceiling only):
*«ninguna pausa puede ser tan grande si estamos hablando con el sistema — a los 5 segundos se apaga»*. He
measured 12-second pauses keeping the mic attentive and ruled them out. The SCALE stays written and running
(it still distinguishes the shapes, and the ceiling is one number to lift if he ever reverses), but MAX_S
now clamps every rung to 5s. Answering after a long delivery still works: V2-655 anchors the window at the
agent's LAST word, and his measured replies arrive ~2s after it.
"""
from __future__ import annotations

MIN_S, MAX_S = 4.0, 5.0
_BASE_S = 8.0
_DIALOGUE_S = 12.0
_ENGAGED_S = 15.0
_ACK_S = 5.0
_ACK_MAX_CHARS = 28          # «Hecho.», «Subo el volumen.», «Aquí lo tienes.» — never a sentence with content


def live_task() -> bool:
    """A Brain Worker session is live for the operator — read from the dispatch registry (the source of truth
    for live sessions, V2-048). Fail-soft False: a broken import must shorten a window, never break a turn."""
    try:
        from nucleo import dispatch
        return bool(dispatch.has_active())
    except Exception:
        return False


def hint(reply: str, *, dialogue_turns: int, task_live: bool | None = None) -> float:
    """Seconds of window the reply that just finished re-anchors. Pure given its inputs (`task_live` is read
    live when not injected); always inside [MIN_S, MAX_S]."""
    r = (reply or "").strip()
    live = live_task() if task_live is None else task_live
    if r.rstrip("»\"'” ").endswith("?") or live:
        w = _ENGAGED_S
    elif dialogue_turns >= 3:
        w = _DIALOGUE_S
    elif r and len(r) <= _ACK_MAX_CHARS and dialogue_turns <= 1:
        w = _ACK_S
    else:
        w = _BASE_S
    return max(MIN_S, min(MAX_S, w))
