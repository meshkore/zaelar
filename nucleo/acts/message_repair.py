"""The message door's repairs: the model's call that falls short of the act he ordered (refactor2710-06 T-02).

  · `ordered_instead` / `run_ordered` — live bench E3, «send the invoice to quinn…»: the turn read as an ORDER at
    1.00, its act `mensajeria:forward` at 0.79, and the model only wrote a `draft`. When the verdict is sure of an act
    that LEAVES at the operator's own bar and the model's call does not leave, the verdict's act runs with the words
    the model wrote and the person his sentence names. Never to somebody his words did not name.
  · `forward_of` / `forward_instead` — a reply to someone else is a FORWARD (demo pass 110 E3): his sentence names
    exactly ONE person of the directory and that person is not who the reply would reach.
"""
from __future__ import annotations

from loguru import logger


def _note(what: str) -> None:
    logger.debug(f"acts.message_repair: {what}")


def _target(db: dict, n):
    """The item `reply` would answer — the same duality `mensajeria.actions._a_reply` resolves."""
    from widgets.mensajeria import data as _d
    if db.get("active_chat") is not None:
        return next((it for it in _d._renumber(db.get("items", [])) if it.get("n") == n), None)
    chat = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None)
    if not chat:
        return None
    key = (chat["platform"], str(chat["chatId"]))
    msgs = [it for it in db.get("items", []) if (it.get("platform"), str(it.get("chatId"))) == key]
    return msgs[-1] if msgs else None


def _is_him(person: dict, item: dict) -> bool:
    from nucleo.acts.message import _TOK
    hay = " ".join(str(item.get(k) or "") for k in ("from", "who", "senderId", "chatId")).lower()
    return any(t in hay for t in _TOK.findall(" ".join(str(person.get(k) or "") for k in ("name", "email")).lower()))


def forward_of(widget_id: str, action: str, payload: dict, said: str) -> dict | None:
    """The `forward` payload this `reply` really is, or None. Never raises."""
    try:
        if (widget_id or "").split("::")[0] != "mensajeria" or action != "reply" or not isinstance(payload, dict):
            return None
        from nucleo.flash import direct_action as _da
        if "contact" not in _da._payload_spec("mensajeria", "forward"):
            return None
        from widgets.contactos import data as _ct
        named = _ct.people_named(said or "")
        if len(named) != 1 or not named[0].get("name"):
            return None
        from widgets.mensajeria import data as _md
        item = _target(_md.load_db(), payload.get("n"))
        if not item or not item.get("messageId") or _is_him(named[0], item):
            return None
        out = {"contact": str(named[0]["name"]), "messageId": str(item["messageId"])}
        return {**out, "text": str(payload["text"])} if str(payload.get("text") or "").strip() else out
    except Exception as e:  # noqa: BLE001
        _note(f"no forward read ({e!r})")
        return None


def forward_instead(widget_id: str, action: str, payload: dict, said: str) -> str:
    """`"forward"` when the model's `reply` is a forward to the person he named, else `""`."""
    return "forward" if forward_of(widget_id, action, payload, said) else ""


def ordered_instead(brief, widget_id: str, model_action: str, payload: dict | None,
                    said: str) -> tuple[str, dict] | None:
    """`(action, payload)` of the ordered act that leaves, to run in place of the model's call, or None."""
    try:
        from nucleo.flash import direct_action as _da, frontend as _fe, undecided as _und
        verdict = _da.completes(brief, widget_id, model_action=model_action)
        if not verdict or not _fe.at_least_sensitive(widget_id, verdict) or _fe.at_least_sensitive(widget_id, model_action):
            return None
        if not _und.sure_order(brief, widget_id, verdict):
            return None
        from nucleo.flash import payload_fill as _pf
        keys = set(_pf._payload_spec(widget_id, verdict))
        pay = dict(payload or {})
        out = forward_of(widget_id, model_action, pay, said) or {
            k: v for k, v in pay.items() if k in keys and str(v or "").strip()}
        out.update(_pf.person_fill(widget_id, verdict, out, said))
        from nucleo.acts import message as _msg
        if not out or _msg.unnamed_recipients(widget_id, verdict, out, said):
            return None
        return verdict, out
    except Exception as e:  # noqa: BLE001 — the model's own call stands
        _note(f"ordered send skipped — {type(e).__name__}: {e}")
        return None


def run_ordered(brief, widget_id: str, model_action: str, payload: dict | None, said: str, *, emit, acted: dict,
                apply) -> bool:
    """The voice rail: run the ordered act instead of the model's call, say so on the timeline; True when it ran."""
    sent = ordered_instead(brief, widget_id, model_action, payload, said)
    if not sent:
        return False
    emit("brain", "📤 orden segura de un acto que sale y el modelo solo lo preparó — corre el veredicto",
         text=f"{widget_id}: modelo={model_action} · veredicto={sent[0]}", role="system",
         extra={"cat": "flash", "id": widget_id, "model": model_action, "verdict": sent[0]})
    acted["widget"] = True
    apply(widget_id, sent[0], sent[1])
    return True
