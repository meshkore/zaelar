"""A promise of work handed over LATER starts its errand (V2-794; split from `promise_kept`, V2-831 audit A10b): the
deferred errand a «you'll have it in a while» owes, its start line, and whether this turn reached a worker at all."""
from __future__ import annotations

from loguru import logger as _log

from nucleo.turn.promise_kept import JUDGED, STARTED


def deferred_errand(reply: str, outcome: dict | None, *, acted: bool, model_calls=(), brief=None) -> bool:
    """Does this turn owe an ERRAND rather than a «not done»? «You'll have them in a while» after a sure `escalate`, with
    nothing run or routed, no model call (a call a guard ate is the honest line's case) and no pass that ran, refused
    or was swallowed: only a worker can keep it. Pure; never raises."""
    try:
        if acted or str((outcome or {}).get("kind") or "") not in ("", JUDGED) \
                or any(isinstance(c, dict) and c.get("name") for c in (model_calls or ())):
            return False
        from nucleo.turn import reply as _reply
        return _reply.owes_an_act(brief) == "escalate"
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: deferred_errand failed: {_e!r}")
        return False


def start_deferred(reply: str, outcome: dict | None, *, acted: bool, brief, model_calls, op_text: str, escalate,
                   emit) -> bool:
    """The voice door: start the errand a deferred promise owes, through the turn's own escalation (the same portal
    every escalation crosses). True when it was started — the turn end then owes no line."""
    if escalate is None or not (op_text or "").strip() or not deferred_errand(reply, outcome, acted=acted,
                                                                              model_calls=model_calls, brief=brief):
        return False
    try:
        from nucleo import surfaces as _surf
        escalate(op_text, context={"src": "voice", "surface": _surf.from_brief(brief), "promised": (reply or "")[:300]})
        if outcome is not None:
            outcome["kind"] = STARTED
        emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=op_text[:200], role="system",
             extra={"cat": "flash", "kind_diag": "promise_started", "reply": (reply or "")[:160]})
        return True
    except Exception as _e:  # noqa: BLE001
        _log.warning(f"promise_kept: the deferred errand could not start: {_e!r}")
        return False


def say_the_start(escalate_req: dict, spoken_text: str, *, send, speech) -> str:
    """An errand a door started in the model's place («⚖️ a commission, not a play») on a turn that said nothing: its
    start line (`escalate_req["say"]`, the i18n «I'm on it — it isn't done yet»), so the turn is not mute. ""."""
    line = str((escalate_req or {}).pop("say", "") or "").strip()
    if not line or (spoken_text or "").strip():
        return ""
    send(speech.sanitize(line, drop_metadata=False))
    return line


def an_errand_was_reached() -> bool:
    """This turn STARTED a worker, injected into one or answered one — whatever lane did it (`consequence.reached`).
    Then its verdict is `started`, never «not done» (refactor2710-99, docs-report-lands-as-document__es)."""
    try:
        from nucleo import consequence
        return consequence.reached("worker.spawn", "worker.inject", "worker.answer")
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: errand reach unreadable: {_e!r}")
        return False
