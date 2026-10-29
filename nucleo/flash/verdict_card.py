"""A SURE verdict on the card in front wins over a model VIEW on another card (demo pass 114, I3, 2026-10-05): «open
the second one» over the F40 photos read `imagenes:select` 0.97 while the model called `results:detail` on the sheet
behind. CRIT-K2 lets a valid model call beat a disagreeing verdict, but compared only calls on the SAME card; across two
open cards with both calls lenses nothing irreversible is at stake, so at ≥ 0.95 the verdict's action runs instead,
through `direct_action.complete`. Anything else is today's rule. Also: the ONE canvas-or-inner-op reader."""
from __future__ import annotations

SURE = 0.95


def _other_view(brief, model_card: str, model_action: str, operator_text: str = "") -> tuple[str, str]:
    """`(card, action)` of a sure verdict VIEW on another open card, when the model's call is a view too — or on the
    SAME card when a sure close names it (`a_view_his_close_names`)."""
    from nucleo.flash import data_ops as _do, direct_action as _da
    vwid, vact = _da.from_brief(brief)               # re-validated against what is still open
    if vwid and _da._base_of(vwid) == _da._base_of(model_card):
        return (vwid, vact) if a_view_his_close_names(brief, model_card, model_action, operator_text) else ("", "")
    if not vwid or not vact:
        return "", ""
    if not _da._action_sure(brief, floor=SURE):
        return "", ""
    if not (_do.is_view_op(model_card, model_action) and _do.is_view_op(vwid, vact)):
        return "", ""
    return vwid, vact


def a_view_his_close_names(brief, card: str, model_action: str, operator_text: str = "") -> str:
    """The card's own VIEW a sure close names, over the model's view on that card; "" otherwise. agenda-everyday-edits
    ES (2026-10-15): «Vale, ya la puedes cerrar» read canvas=close 1.00 AND `agenda:close_meeting` 1.00, the model
    called `open_meeting`, and the short-close shortcut shut the whole AGENDA. Two lenses, nothing irreversible
    either way, and the close says the model's reading is the one he did not ask for. Never raises."""
    try:
        from nucleo.flash import data_ops as _do, direct_action as _da
        vwid, vact = _da.from_brief(brief)
        if not vwid or not vact or vact == model_action or _da._base_of(vwid) != _da._base_of(card):
            return ""
        if inner_order_wins(brief, operator_text) != "sure":
            return ""
        return vact if _do.is_view_op(card, model_action) and _do.is_view_op(vwid, vact) else ""
    except Exception:  # noqa: BLE001
        return ""


def takes_the_view(brief, model_card: str, model_action: str, *, operator_text: str, emit, present,
                   apply_widget_data) -> str:
    """The voice rail: run the verdict's view instead of the model's — or its action instead of the model's removal
    (`destructive_veto`) — or "". Never raises."""
    try:
        from nucleo.flash import destructive_veto as _dv
        if (swap := _dv.instead(brief, model_card, model_action, operator_text)):
            return _dv.run(swap, model_action, emit=emit, apply_widget_data=apply_widget_data)
        vwid, vact = _other_view(brief, model_card, model_action, operator_text)
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
    """The text channel's `(widget, action, payload)`: a reply that is a forward (`acts.message`), or the
    verdict's view on the card in front over a model view on another. Unchanged otherwise. Never raises."""
    try:
        from nucleo.acts import message as _msg
        from nucleo.flash import destructive_veto as _dv
        if (swap := _dv.instead(brief, widget_id, action, said)):
            return swap                              # never a removal over a sure verdict that names another act
        if (sent := _msg.ordered_instead(brief, widget_id, action, payload, said)):
            return widget_id, sent[0], sent[1]       # an ordered act that leaves, which the model only prepared
        if (fw := _msg.forward_of(widget_id, action, payload, said)):
            return widget_id, "forward", fw
        vwid, vact = _other_view(brief, widget_id, action, said) or ("", "")
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
    from nucleo.flash import data_ops as _do, direct_action as _da
    from nucleo.turn import brief as _tb
    vwid, vact = _da.from_brief(brief)
    if not vwid or _da._base_of(vwid) != _da._base_of(model_card):    # the voice rail's bar: the verdict was USED
        return "", ""
    words = str(_tb.read(brief, _tb.WORDS_KEY, "")[0] or "")
    return (vwid, vact) if _do.a_view_where_the_verdict_acts(model_card, model_action, vact, words) else ("", "")


def canvas_yields(brief) -> bool:      # the data completion's question (V2-781 pair 5), asked of the one reader
    return inner_op_may_run(brief)


def inner_op_may_run(brief, operator_text: str = "", *, builds_payload: bool = False) -> bool:
    """THE one reader of «canvas gesture or inner op» for every pass (sandbox 2026-10-29 C6: the promise repair ran close_meeting
    0.50 under close 1.00). Close/arrange yield only to `inner_order_wins`, other gestures to an inner op as sure."""
    try:
        from nucleo.flash import direct_action as _da
        brief = brief if brief is not None else __import__("nucleo.turn.brief", fromlist=["x"]).of_this_turn()
        if (gesture := _da.sure_canvas(brief)) not in ("close", "arrange"):
            return not gesture or _da._action_sure(brief, floor=SURE)
        return (why := inner_order_wins(brief, operator_text)) == "sure" or (why == "write" and builds_payload)
    except Exception:  # noqa: BLE001
        return True


def inner_order_wins(brief, operator_text: str = "") -> str:
    """Why a SURE «close» verdict must NOT close the card it lands on: "sure", "write", or "" (the close stands).

    The canvas question reads every removal verb as «close» (`agenda-everyday-edits` ES, 2026-10-11: «ya la puedes
    cerrar» close 1.00 AND close_meeting 1.00; «quita el piano entero» close 0.91 AND cancel_meeting 0.71 — the AGENDA
    closed both times). "sure": an action of the card as sure as the close (≥ SURE) runs. "write": a WRITE of the card
    (not a lens, not its own close) is left to the repair that builds its payload. His words naming a card keep the
    close. «arrange» (canvas=arrange 0.92 AND results:layout 1.00, sandbox 2026-10-28 S2) has only the "sure" rung."""
    try:
        from nucleo.flash import data_ops as _do, direct_action as _da
        gesture = _da.sure_canvas(brief)
        if gesture not in ("close", "arrange"):
            return ""
        owner, name = _da.from_brief(brief)
        if not owner or not name or _da.named_cards(operator_text):
            return ""
        if _da._action_sure(brief, floor=SURE):
            return "sure"
        if gesture != "close":
            return ""
        return "write" if name != "close" and not _do.is_view_op(owner, name) else ""
    except Exception:  # noqa: BLE001 — a doubt keeps today's close
        __import__("logging").getLogger("zaelar.flash").debug("inner_order_wins failed", exc_info=True)
        return ""


def close_is_owed(brief, operator_text: str = "") -> bool:
    """The voice promise door's «it promised to CLOSE»: a sure close verdict the inner order does not outrank."""
    from nucleo.flash import direct_action as _da
    return _da.sure_canvas(brief) == "close" and not inner_order_wins(brief, operator_text) \
        and not __import__("nucleo.turn.brief", fromlist=["x"]).names_elsewhere(brief, against_a_call=True)
