"""A SURE verdict on the card in front wins over a model VIEW on another card (demo pass 114, I3, 2026-10-05).

«open the second one» with the F40 photos on screen: the verdict read `imagenes:select` at 0.97, the model called
`results:detail {index: 2}` on the monitors sheet behind them, and «opening the LG 27US500-W» was said over a car.
CRIT-K2 lets a valid model call beat a disagreeing verdict, because a wrong verdict costs a reversible view — but
it compared only calls on the SAME card (pass 85 had the same shape). Across two open cards, with both calls
being lenses (`"view": true`), nothing irreversible is at stake either way, and the verdict is the only reader
that saw which card was in front. So at ≥ 0.95 the verdict's own action runs instead, through the same
`direct_action.complete` door (its payload resolved from his words, the same gate every call passes).

Anything else — a write on either side, the verdict on the same card, an unsure or closed one — is today's rule.
"""
from __future__ import annotations

SURE = 0.95


def _other_view(brief, model_card: str, model_action: str) -> tuple[str, str]:
    """`(card, action)` of a sure verdict VIEW on another open card, when the model's call is a view too."""
    from nucleo.flash import data_ops as _do, direct_action as _da
    vwid, vact = _da.from_brief(brief)               # re-validated against what is still open
    if not vwid or not vact or _da._base_of(vwid) == _da._base_of(model_card):
        return "", ""
    if not _da._action_sure(brief, floor=SURE):
        return "", ""
    if not (_do.is_view_op(model_card, model_action) and _do.is_view_op(vwid, vact)):
        return "", ""
    return vwid, vact


def takes_the_view(brief, model_card: str, model_action: str, *, operator_text: str, emit, present,
                   apply_widget_data) -> str:
    """The voice rail: run the verdict's view instead of the model's, or "". Never raises."""
    try:
        vwid, vact = _other_view(brief, model_card, model_action)
        if not vwid:
            return ""
        from nucleo.flash import direct_action as _da
        done = _da.complete(brief, operator_text=operator_text, emit=emit, present=present,
                            apply_widget_data=apply_widget_data, widget_id=vwid, instead_of=model_action,
                            require_order=False)
        if done:
            emit("brain", "🎯 veredicto seguro sobre la tarjeta de delante — corre su vista, no la del modelo",
                 text=f"modelo={model_card}:{model_action} · veredicto={vwid}:{vact}", role="system",
                 extra={"cat": "flash", "id": vwid, "model": f"{model_card}:{model_action}", "verdict": vact})
        return done
    except Exception:  # noqa: BLE001
        return ""


def retarget(brief, widget_id: str, action: str, payload: dict, said: str) -> tuple[str, str, dict]:
    """The text channel's `(widget, action, payload)`: a reply that is a forward (`reply_or_forward`), or the
    verdict's view on the card in front over a model view on another. Unchanged otherwise. Never raises."""
    try:
        from nucleo.flash import reply_or_forward as _rof
        if (fw := _rof.forward_of(widget_id, action, payload, said)):
            return widget_id, "forward", fw
        vwid, vact = _other_view(brief, widget_id, action) or ("", "")
        if not vwid:
            vwid, vact = _act_over_a_lens(brief, widget_id, action)
        if vwid:
            from nucleo.flash import direct_action as _da
            rung = _da.resolve(said, brief=brief, operator_text=said)
            if rung and rung.get("action") == vact and isinstance(rung.get("payload"), dict):
                return str(rung.get("widget") or vwid), vact, rung["payload"]
    except Exception:  # noqa: BLE001 — the model's own call stands
        __import__("logging").getLogger("zaelar.flash").warning("verdict_card.retarget failed", exc_info=True)
    return widget_id, action, payload


def _act_over_a_lens(brief, model_card: str, model_action: str) -> tuple[str, str]:
    """The voice rail's `data_ops.a_view_where_the_verdict_acts`, for the text channel (V2-781 pair 5: «cámbiale el
    nombre al dentista» → verdict update_meeting 0.99, model open_meeting, «Hecho»; «quita el piano entero» → verdict
    cancel_meeting 0.81, model show_day, «Hecho»). Same card, the verdict USED — the voice rail's bar (`completes`)."""
    from nucleo.flash import data_ops as _do, direct_action as _da, turn_brief as _tb
    vwid, vact = _da.from_brief(brief)
    if not vwid or _da._base_of(vwid) != _da._base_of(model_card):    # the voice rail's bar: the verdict was USED
        return "", ""
    words = str(_tb.read(brief, _tb.WORDS_KEY, "")[0] or "")
    return (vwid, vact) if _do.a_view_where_the_verdict_acts(model_card, model_action, vact, words) else ("", "")


def canvas_yields(brief) -> bool:
    """No sure canvas gesture, or an inner op as SURE as one (V2-781 pair 5: «ya la puedes cerrar» read canvas=close
    1.00 AND agenda:close_meeting 1.00, and the sheet stayed open). The R4/M4 misses had the inner op at 0.55-0.60."""
    from nucleo.flash import direct_action as _da
    return not _da.sure_canvas(brief) or _da._action_sure(brief, floor=SURE)
