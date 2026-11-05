"""A SURE «escalate» verdict routes the request to the errand portal before the model is trusted (V2-851 F5, CRIT-E27).

The brief's `escalate_or_inline` question is answered in the turn's one Jev trip. When it is SURE — at or above the
licence (`verdicts.LICENCE`), the verdict the declared task clauses produce (a document, a reply drafted from his mail)
— the one router decides: the request goes to the errand portal (`escalate_req` → the close's launch →
`acts/errand` → `flow_door` → `flow_of.route`), whether or not the model called `escalate_to_slowbrain`, and the
model's inline act or answer of that turn is NOT executed: no inline `reply`, no send. The turn's one line is the
start line the close already says for an escalation with no words («on it»).

Not a re-run after the stream: the verdict is read where the model's output is held anyway — at its first word
(`follow_up_pass.Hold`) and at each call it makes (`gate_calls`) — waiting for a brief in flight at most `wait_s()`.
Measured on battery C9 before this (2026-11-05): the verdict flipped to escalate at 0.52-0.62 and Flash still answered
inline, sending what should have waited for his consent inside a task.
"""
from __future__ import annotations

import os
import time

from loguru import logger

#: The calls a routed turn still lets through: the commission itself, and the model saying it could not read him.
PASS = frozenset({"escalate_to_slowbrain", "not_understood"})


def wait_s() -> float:
    """How long the model's words and calls wait for a brief in flight before they run on their own."""
    try:
        return max(0.0, float(os.getenv("ZAELAR_ROUTE_WAIT_S", "1.5")))
    except ValueError:
        return 1.5


def sure_escalate(brief) -> bool:
    """The brief's escalate verdict is SURE (≥ the licence) — never waits, never raises."""
    try:
        from nucleo.turn import brief as _tb, verdicts as _v
        choice, info = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=_v.LICENCE)
        return bool(info) and bool(info.get("used", True)) and choice == "escalate"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"route_by_verdict: unreadable verdict — {e!r}")
        return False


def ready(brief) -> bool:
    try:
        from nucleo import jev
        return bool(brief) and jev._is_ready(brief)
    except Exception:  # noqa: BLE001
        return True


def decided(brief, t0: float, wait: float):
    """True/False once the verdict can be read, None while the brief is in flight and the wait has not passed."""
    if brief and not ready(brief) and time.monotonic() - t0 < wait:
        return None
    return sure_escalate(brief)


def gate_calls(on_tool_call, *, brief, escalate_req: dict, operator_text: str, emit, t0: float, wait: float):
    """The model's calls through the verdict: under a sure «escalate» an inline call is not run and the request is
    the commission. A brief still in flight is waited for, at most what is left of `wait` since `t0`."""
    def _call(name, args):
        if name not in PASS and brief and not ready(brief):
            left = wait - (time.monotonic() - t0)
            if left > 0:
                try:
                    brief["event"].wait(left)
                except Exception as e:  # noqa: BLE001 — an unawaitable brief reads as in flight
                    logger.debug(f"route_by_verdict: brief not awaited — {e!r}")
        if name not in PASS and sure_escalate(brief):
            route(escalate_req, operator_text, emit, why=f"call:{name}")
            return None
        return on_tool_call(name, args)
    return _call


def owns(escalate_req: dict | None) -> bool:
    """The request was routed by a sure verdict: it is the turn's commission, final — no later step of the close
    swaps it for a card act, a show or a picture search, or annuls it (battery C9: the third rung ran the messaging
    card's `reply` inline on a routed «answer that mail», and the consent his mail's taint asks for never came)."""
    return bool((escalate_req or {}).get("routed"))


def route(escalate_req: dict, operator_text: str, emit, *, why: str) -> None:
    """The request is the turn's commission (the errand portal launches it at the close, through `flow_of.route`)."""
    first = not escalate_req.get("routed")
    escalate_req["routed"] = True
    if escalate_req.get("v") is None:
        escalate_req["v"] = operator_text
    if first:
        emit("brain", "🧭 sure escalate verdict — the request goes to its task, nothing runs inline", role="system",
             text=str(operator_text or "")[:160], extra={"cat": "flash", "why": why, "routed": True})
