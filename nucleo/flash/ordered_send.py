"""An ORDERED act that leaves is carried out when the model only prepared it (2026-10-15, the operator's 70%).

Live bench E3, «send the invoice to andrew, tell him we're already trying inworld and he should book it»: the turn
was read as an ORDER at 1.00 and its action as `mensajeria:forward` at 0.79, and the model called `draft` — a reply
written in the box and left there. Two runs in seven ended with nothing sent and «Done.» said.

This is the mirror of the rule that already stands in the voice executor (demo pass 2026-09-28, full12 E3): when the
MODEL's call leaves and the verdict names another act, the verdict runs — a mail nobody asked for is the costly
reading. Here the costs are the other way round: he asked for the act that leaves, the verdict is sure of it at the
operator's own bar (`consent.intent_act_at`), and the model's call stops short of it. The verdict's act runs, with
the words the model already wrote and the person his sentence names.

Below the bar, or with the model's call leaving too, or with the two readers agreeing, nothing changes here. And the
engine never ORIGINATES a send to somebody his words did not name (`leave_gate.unnamed_recipients`, the operator's
2026-10-15 rule: who it goes to is never a doubt) — the model's draft stays a draft.
"""
from __future__ import annotations

from loguru import logger


def instead(brief, widget_id: str, model_action: str, payload: dict | None, said: str) -> tuple[str, dict] | None:
    """`(action, payload)` of the ordered act that leaves, to run in place of the model's call, or None. Never raises."""
    try:
        from nucleo.flash import direct_action as _da, frontend as _fe, undecided as _und
        verdict = _da.completes(brief, widget_id, model_action=model_action)
        if not verdict or not _fe.at_least_sensitive(widget_id, verdict) or _fe.at_least_sensitive(widget_id, model_action):
            return None
        if not _und.sure_order(brief, widget_id, verdict):
            return None
        from nucleo.flash import payload_fill as _pf, reply_or_forward as _rof
        keys = set(_pf._payload_spec(widget_id, verdict))
        pay = dict(payload or {})
        out = _rof.forward_of(widget_id, model_action, pay, said) or {
            k: v for k, v in pay.items() if k in keys and str(v or "").strip()}
        out.update(_pf.person_fill(widget_id, verdict, out, said))
        from nucleo.flash import leave_gate as _lg
        if not out or _lg.unnamed_recipients(widget_id, verdict, out, said):
            return None
        return verdict, out
    except Exception as e:  # noqa: BLE001 — the model's own call stands
        logger.debug(f"ordered_send: skipped — {type(e).__name__}: {e}")
        return None


def run(brief, widget_id: str, model_action: str, payload: dict | None, said: str, *, emit, acted: dict, apply) -> bool:
    """The voice rail: run the ordered act instead of the model's call, say so on the timeline; True when it ran."""
    sent = instead(brief, widget_id, model_action, payload, said)
    if not sent:
        return False
    emit("brain", "📤 orden segura de un acto que sale y el modelo solo lo preparó — corre el veredicto",
         text=f"{widget_id}: modelo={model_action} · veredicto={sent[0]}", role="system",
         extra={"cat": "flash", "id": widget_id, "model": model_action, "verdict": sent[0]})
    acted["widget"] = True
    apply(widget_id, sent[0], sent[1])
    return True
