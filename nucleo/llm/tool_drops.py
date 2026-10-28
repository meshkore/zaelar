"""nucleo/llm/tool_drops.py — actions the model took and the system could not read, kept as FACTS.

Split out of `fast_client.py` (which re-exports these names) so the client stays within its size ceiling; the
record is the same one the stream fills (`_drop_tool_call`) and the next turn reads (`recent_drops`).
"""
from __future__ import annotations

import time

from loguru import logger


# Actions the system threw away, kept just long enough to be said in the NEXT turn. Same remedy as
# `widgets/navegador/tasks.recently_finished()` (V2-150) and `dispatch._EXPIRED_CONFIRM` (V2-190): a fact that
# only exists for one turn is a fact the conversation loses.
_RECENT_DROPS: list[dict] = []
_DROP_MEMORY_S = 180.0     # the immediate conversation, no more: an action dropped ten minutes ago is history


def recent_drops(now: float | None = None) -> list[dict]:
    """Actions dropped in the last few minutes — for the live state, so the next turn can say so."""
    now = time.time() if now is None else now
    return [d for d in _RECENT_DROPS if now - float(d.get("at") or 0) <= _DROP_MEMORY_S]


def clear_drops() -> None:
    """Called once the fact has been said, so it is not repeated forever."""
    _RECENT_DROPS.clear()


def _drop_tool_call(metrics: dict, name: str, raw_args: str) -> None:
    """An action the model decided to take and the system could not read. Record it as a FACT.

    It used to be a bare `continue` under a `logger.warning`, and that is why V2-171 was invisible for three
    days: the user was told «te pongo con ello», nothing ran, and neither the operator, nor the judge, nor the
    observability viewer had any way to know. From a conversation log it reads as the assistant lying. It did not lie — its
    action was thrown away.

    Raising the cap (see `_DEFAULT_MAX_TOKENS`) removes the cause that was measured, but not the class: any
    model can emit malformed JSON. What this guarantees is that when it happens the loss is KNOWN, which is
    the whole difference between a bug and a mystery. Best-effort throughout — reporting a dropped action must
    never be able to drop the turn as well.
    """
    # Three different facts used to wear one label. «argumentos ilegibles» covered the token cap (until
    # V2-171 named it), a genuinely malformed object, AND a stream that never finished — and the third is the
    # common one: measured 2026-09-03 (Soria reservation, 16:02:47), the operator barged in mid-escalation,
    # the turn was RETAINED, the stream closed with no finish_reason, and the half-accumulated arguments were
    # filed as «illegible», sending the diagnosis toward «the model emits broken JSON» when the model was
    # interrupted mid-sentence. An unfinished stream is not a model defect, and the fix for each is different.
    _fr = str(metrics.get("finish_reason") or "")
    if _fr == "length":
        reason = "cortada por el tope de tokens"
    elif not _fr:
        reason = "el stream se cortó a mitad de la acción (interrupción del turno o corte de red)"
    else:
        reason = "argumentos ilegibles"
    logger.warning(f"tool call {name} DESCARTADA ({reason}): {(raw_args or '')[:200]!r}")
    dropped = metrics.setdefault("dropped_tool_calls", [])
    # `args_head` (V2-658): the head of what the model was WRITING travels with the fact. A widget_data
    # cut by the token cap usually begins with id/action/title — enough for the rescue escalation to name
    # the errand instead of apologizing («Perdona, ¿me lo repites?» over a request the turn had in hand).
    dropped.append({"name": name, "reason": reason, "chars": len(raw_args or ""),
                    "args_head": (raw_args or "")[:240]})
    # V2-176 frente 2: and the fact has to OUTLIVE this turn. V2-171 recorded the drop in the turn's own metrics and in
    # observability, which the operator can inspect afterwards — but the NEXT turn saw nothing, so the
    # conversation carried on as if the action had gone out. The sentence «te pongo con ello» was already
    # spoken by then; what can still be fixed is the turn after it.
    _RECENT_DROPS.append({"name": name, "reason": reason, "at": time.time()})
    del _RECENT_DROPS[:-4]
    try:
        from voice.observer import emit
        emit("tool_dropped", "⚠️ acción descartada",
             text=f"{name}: {reason}", extra={"tool": name, "reason": reason,
                                              "finish_reason": metrics.get("finish_reason") or ""})
    except Exception as e:  # noqa: BLE001 — reporting a drop must never drop the turn too
        logger.debug(f"tool_drops: the timeline row could not be written: {e}")


def oversized_widget_write(metrics: dict | None) -> str | None:
    """A `widget_data` this turn that was cut by the TOKEN CAP — the model tried to hand a widget MORE
    CONTENT than a voice turn can carry (V2-658, measured 2026-09-10, session 0d070761: the full text of
    the Declaration of Independence pasted inline into `documento`; `finish_reason: length`, action
    discarded, and the turn fell to «Perdona, ¿me lo repites?» over an errand it had in hand — twice, in
    two consecutive sessions). Returns the head of what it was writing, or None. The caller escalates:
    content that exceeds the turn is a WORKER's delivery (V2-644's doc surface), never a retry inline."""
    for d in (metrics or {}).get("dropped_tool_calls") or []:
        if d.get("name") == "widget_data" and "tope de tokens" in str(d.get("reason") or ""):
            return str(d.get("args_head") or "")[:240] or "(sin cabecera)"
    return None
