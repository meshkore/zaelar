"""The second pass after the model only LOOKED (read a card, searched) while the turn ordered an act: the
call it owed, with what it found.
Moved from `nucleo/flash/act_repair.py` (refactor2710-05 T-04); its names are read through `_ar`."""
from __future__ import annotations

from nucleo.flash import act_repair as _ar


async def call_after_read(operator_text: str, read_widget: str, widget_id: str, spec=None, *,
                          window=None) -> dict | None:
    """The turn READ one card to get what an order on ANOTHER card needed — and the read path ends the turn with
    words only. `{widget_id, action, payload}` for the order, or None. Never raises.

    Demo pass 2026-09-28 (full20 C5): «send rowan a telegram with the new time» — the model read the agenda for the
    new time (sensible), and the read's answer pass, which has no tools, said «I can't send a Telegram, I don't have
    any messaging tool available here». The order stood; this pass carries it out with what was read."""
    try:
        wid = str(widget_id or "").strip().lower()
        rid = str(read_widget or "").strip().lower()
        if not wid or not rid or wid == rid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _ar._widget_data_tool()
        if not declared or not tool:
            return None
        from nucleo.flash import widget_read as _wr
        block = str(_wr.read(rid) or "").strip()[:1500] or "(vacía)"
        digest = str(_wr.read(wid) or "").strip()[:800]
        card = (_ar._CARD.format(wid=wid, digest=digest) if digest else "") + _ar._days()
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _ar._in_his_lang(_ar._SYS_AFTER_READ).format(wid=wid, read=rid, block=block,
                                                                  actions=_ar._actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + _ar.conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            action = str(args.get("action") or "").strip()
            if name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid and action in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": action, "payload": payload}
        _ar._note(wid, "tras leer, el modelo no hizo la llamada de la orden", read=rid)
        return None
    except Exception:  # noqa: BLE001
        return None


def _is_view(wid: str, action: str) -> bool:
    try:
        from nucleo.flash import data_ops as _dops
        return bool(_dops.is_view_op(wid, action))
    except Exception:  # noqa: BLE001
        return False


def same_card_order_after_read(brief, read_widget: str, reply: str = "") -> str:
    """The verdict's action when the turn READ the very card the order is on and stopped there, or "".

    V2-781 T518: «There's no piano on Tuesday October 13» — verdict `agenda:cancel_meeting` at 1.00, the model only
    read, and the brief called it a `comment`, so the order gate stayed shut. A statement about his own card IS an
    order on it when a SURE verdict names a real op there and the brief reads an order — never for a
    question, which a read answers."""
    try:
        from nucleo.turn import brief as _tb
        target, t_info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.85)
        owner, _sep, act = str(target or "").rpartition(":")
        rid = str(read_widget or "").split("::")[0].strip().lower()
        if not (t_info and owner and act) or owner.split("::")[0].lower() != rid:
            return ""
        kind, k_info = _tb.read(brief, _tb.REQUEST_KEY, "")
        sure_order = str(kind or "") == "order" and bool(k_info)
        if str(kind or "") == "question" or (_ar._is_view(rid, act) and not sure_order):   # p124 F2: «go to» is a sure lens
            return ""
        # Only an order the brief is sure of licenses the repair (audit V2-783 P0-3 — «Shall I send it?» was carried
        # out here); what our reply said decides nothing (refactor2710-03).
        return act if sure_order else ""
    except Exception:  # noqa: BLE001
        return ""


async def after_a_read(brief, operator_text: str, read_widget: str, reply: str = "", spec=None, *,
                       window=None) -> dict | None:
    """The order a READ was serving, carried out — `{widget_id, action, payload}` or None. ONE door for both
    channels: the voice read lane and the probe's light route used to differ (only the voice had it).

    Another card («send rowan a telegram with the new time», full20 C5) → `call_after_read`; the same card the
    verdict names (T518) → the verdict's call, asked once like a repeated view."""
    try:
        from nucleo.flash import direct_action as _da
        other = _da.order_card_after_read(brief, operator_text, read_widget)
        if other:
            return await _ar.call_after_read(operator_text, read_widget, other, spec, window=window)
        act = _ar.same_card_order_after_read(brief, read_widget, reply)
        if act:
            rid = str(read_widget or "").split("::")[0]
            return await _ar.call_for_repeated_view(operator_text, rid, "read_widget", act, spec, window=window)
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


def order_card_after_search(brief, answer: str = "") -> str:
    """The card an ORDER is on when the turn SEARCHED the web for the fact it needed, or "".

    V2-781 T515 (2026-10-03): «Can you set a reminder for the premiere day?» — the model searched again for the
    date, and the search's answer pass, which has no tools, said «I can't actually set reminders myself»; the
    brief had read `request_type=order` and `catalog_widget=agenda` (0.91). The ES twin read `wants_words=tell` on
    the same order and `request_type=question` on «¿te enteras de cuándo se estrena y me avisas?» — answered «avisarte
    no puedo». So: a card the brief names, and either a SURE order or an answer that refuses an act. A question
    answered with its fact never reaches here."""
    try:
        from nucleo.flash import build_decision as _bd
        from nucleo.turn import brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=0.8)
        if not ((str(kind or "") == "order" and info) or _ar.denies_the_act(answer)):
            return ""
        return str(_bd.named_card(brief) or "").split("::")[0]
    except Exception:  # noqa: BLE001
        return ""


async def call_after_search(operator_text: str, answer: str, brief, spec=None, *, window=None) -> dict | None:
    """The order half of a turn that searched for its fact — `{widget_id, action, payload}` or None. Never raises.

    The sibling of `call_after_read`: the search's answer pass has no tools, so an order beside the question
    («find out when it premieres and remind me») was answered with the fact and then refused. One bounded pass:
    the card the brief names, its declared actions, the caller's usual gate."""
    try:
        wid = _ar.order_card_after_search(brief, answer)
        if not wid or not (operator_text or "").strip() or not (answer or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _ar._widget_data_tool()
        if not declared or not tool:
            return None
        from nucleo.flash import widget_read as _wr
        digest = str(_wr.read(wid) or "").strip()[:800]
        card = (_ar._CARD.format(wid=wid, digest=digest) if digest else "") + _ar._days()
        said = " ".join(str(answer).split())[:600].replace("{", "(").replace("}", ")")
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _ar._in_his_lang(_ar._SYS_AFTER_SEARCH).format(wid=wid, answer=said, actions=_ar._actions_block(manifest),
                                                                    card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + _ar.conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            action = str(args.get("action") or "").strip()
            if name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid and action in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": action, "payload": payload}
        _ar._note(wid, "tras buscar, el modelo no hizo la llamada de la orden")
        return None
    except Exception:  # noqa: BLE001
        return None


async def voice_after_search(operator_text: str, spoken_text: str, brief, spec, *, window, apply, send, emit,
                             acted: dict, done: dict) -> bool:
    """The VOICE channel's half of `call_after_search`: run the order, mark the turn as having acted, say what
    happened after a refusal that already streamed (`after_the_repair`), and leave one timeline line."""
    got = await _ar.call_after_search(operator_text, spoken_text, brief, spec, window=window)
    if not got:
        return False
    apply(got["widget_id"], got["action"], got["payload"])
    acted["widget"] = done["v"] = True
    line = _ar.after_the_repair(spoken_text, False, got["widget_id"], got["action"]).strip()
    if line:
        send(line)
    emit("brain", "🔁 buscó para una orden — la llamada, con lo encontrado", role="system",
         text=f"{got['widget_id']}:{got['action']}", extra={"cat": "flash", "widget": got["widget_id"],
                                                          "action": got["action"]})
    return True


def _tool_named(name: str) -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None
