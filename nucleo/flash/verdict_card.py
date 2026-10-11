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
    """The voice rail: run the verdict's view instead of the model's — or its action instead of the model's removal
    (`destructive_veto`) — or "". Never raises."""
    try:
        from nucleo.flash import destructive_veto as _dv
        if (swap := _dv.instead(brief, model_card, model_action, operator_text)):
            return _dv.run(swap, model_action, emit=emit, apply_widget_data=apply_widget_data)
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
        from nucleo.flash import destructive_veto as _dv, reply_or_forward as _rof
        if (swap := _dv.instead(brief, widget_id, action, said)):
            return swap                              # never a removal over a sure verdict that names another act
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


def inner_order_wins(brief, operator_text: str = "") -> str:
    """Why a SURE «close» verdict must NOT close the card it lands on: "sure", "write", or "" (the close stands).

    The canvas question can only answer show / close / neither, so every removal verb reaches it as «close». Measured
    in `agenda-everyday-edits` (ES, 2026-10-11): «ya la puedes cerrar» read canvas=close 1.00 AND
    `agenda:close_meeting` 1.00; «quita el piano entero, toda la serie» read canvas=close 0.91 AND
    `agenda:cancel_meeting` 0.71. Both times the canvas completion ran first and closed the whole AGENDA, «Hecho.»
    was said over it, and the action verdict — the one reader that knew WHAT his words remove — was never read.
    `canvas_yields` already let a sure inner op win (V2-781 pair 5), but only at the data completion, which the
    canvas completion pre-empted: the rule lived on one of two branches.

      · "sure"  — the verdict names an action of the card as surely as the close (≥ SURE): that action runs.
      · "write" — the verdict names a WRITE of the card (not a lens, not its own close): the close is the canvas
        question's reading of a removal verb, and the write is left to the repair that builds its payload.
    His words naming a card («cierra la agenda») keep the close: the canvas verdict is then about that card.
    Never raises."""
    try:
        from nucleo.flash import data_ops as _do, direct_action as _da
        if _da.sure_canvas(brief) != "close":
            return ""
        owner, name = _da.from_brief(brief)
        if not owner or not name or _da.named_cards(operator_text):
            return ""
        if _da._action_sure(brief, floor=SURE):
            return "sure"
        return "write" if name != "close" and not _do.is_view_op(owner, name) else ""
    except Exception:  # noqa: BLE001 — a doubt keeps today's close
        __import__("logging").getLogger("zaelar.flash").debug("inner_order_wins failed", exc_info=True)
        return ""


def close_is_owed(brief, operator_text: str = "") -> bool:
    """The voice promise door's «it promised to CLOSE»: a sure close verdict the inner order does not outrank."""
    from nucleo.flash import direct_action as _da
    return _da.sure_canvas(brief) == "close" and not inner_order_wins(brief, operator_text)
