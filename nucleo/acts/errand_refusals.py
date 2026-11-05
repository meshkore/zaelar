"""nucleo/acts/errand_refusals.py — what the errand door does when it refuses (V2-655, V2-852 T21, V2-854 F4).

Split from `nucleo/acts/errand.py` by concern: the portal decides (the core is not modified; a stopped agent opens
nothing) before any id or row exists, and these are the refusals it then owes — a timeline row and one line through
the turn's mouth, never «nothing happened» as the only trace; a stopped refusal also closes its flow.
"""
from __future__ import annotations

from loguru import logger


def refuse_engine(req: str, reason: str) -> None:
    """The refusal TRAVELS: to him by the turn's mouth (out of turn when no turn of his is live, `turn/mouth`) and to
    the timeline — «nothing happened» is never the only trace."""
    try:
        from voice.observer import emit
        emit("task", "blocked", role="system", text=req[:120],
             extra={"reason": "el núcleo y el motor no se modifican desde la voz ni el chat"})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"escalate: the engine refusal left no timeline row — {e!r}")
    try:
        from nucleo.turn import mouth
        mouth.say(reason, verdict="cannot", door="errand", key="errand:refused:engine")
    except Exception as e:  # noqa: BLE001 — the timeline row above already records it
        logger.debug(f"escalate: the engine refusal was not said — {e!r}")
    logger.info(f"escalate: RECHAZADA — pide modificar el motor: {req[:80]}")


def refuse_stopped(req: str, ctx: dict | None = None) -> None:
    """The errand did not start because the agent is stopped (⏻): one `task/blocked` row and one line, the door's
    `cannot`, through the turn's mouth (out of turn when no turn of his is live) — and its flow closed explicitly,
    as the listener's refusal did (V2-113: the turn marked the trace just-escalated, and no session will close it)."""
    try:
        trace = str((ctx or {}).get("trace") or "")
        if not trace:
            from voice import trace as _trace
            trace = _trace.current() or ""
        from nucleo import dispatch as _d
        _d._close_escalated_flow({"trace": trace}, ok=False, status="rejected_halted")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"escalate: the refused flow was not closed — {e!r}")
    try:
        from voice.observer import emit
        emit("task", "blocked", role="system", text=req[:120], extra={"reason": "agent stopped (⏻): no new work opens"})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"escalate: the stopped refusal left no timeline row — {e!r}")
    try:
        from i18n import langs
        from nucleo.circuit import verdict as V
        from nucleo.turn import mouth
        line = str(getattr(langs.current_language(), "errand_not_started_stopped", "") or "")
        mouth.say(line.format(request=req[:120]), verdict=V.CANNOT.name, door="errand", key=f"errand:refused:stopped:{abs(hash(req)) % 10**8}")
    except Exception as e:  # noqa: BLE001 — the timeline row above already records it
        logger.debug(f"escalate: the stopped line was not said — {e!r}")
    logger.info(f"escalate: REFUSED — the agent is stopped: {req[:80]}")
