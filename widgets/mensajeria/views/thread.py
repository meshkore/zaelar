#
# views/thread.py — the read side of ONE conversation: resolving a spoken chat name, the conversation view a
# thread renders from, its meta, and `peek` (a conversation handed whole to the brain). Same one-directional seam
# as the rest of `views/`: anything that needs data.py imports it LAZILY inside the function.
#
import unicodedata

from .chats import _group_chats


_PEEK_MAX_MSGS = 40                  # = thread.KEEP: everything a thread can hold live
_PEEK_MAX_BODY = 500
_PEEK_BUDGET = 7000                  # total chars of message text one answer may carry into the turn


def _norm_txt(s) -> str:
    """Accent-stripped lowercase, for matching a spoken chat name against the list."""
    s = unicodedata.normalize("NFD", str(s or "").strip().lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _known_chats(db: dict) -> list:
    """Conversations we HOLD, pending or not (V2-546). The main list stays an INBOX — what still wants
    attention — and that is deliberate: showing every recent chat there would turn a triage surface into a
    second messaging app. But a conversation the operator has already dealt with is still one he can read, so
    `open` resolves against these too. Without it, answering someone from your phone makes their chat
    unopenable here: it leaves the inbox, and the inbox was the only index."""
    out = []
    for k, th in (db.get("threads") or {}).items():
        platform, _, chat_id = str(k).partition("|")
        if not chat_id or not isinstance(th, dict):
            continue
        name = th.get("name") or ""
        if not name:
            for m in th.get("msgs") or []:
                if m.get("dir") == "in" and m.get("who"):
                    name = m["who"]
                    break
        out.append({"platform": platform, "chatId": chat_id, "name": name or chat_id,
                    "touched": float(th.get("touched") or 0)})
    out.sort(key=lambda c: -c["touched"])
    return out


def _find_chat_by_name(db: dict, name: str):
    """Resolve a spoken chat name against the pending list FIRST and the conversations we hold second. Order
    matters: what is on screen wins over what is merely remembered."""
    want = _norm_txt(name)
    if not want:
        return None
    from .. import data as _d
    from .. import names as _names
    # The names he SEES are the names he says (V2-819): the pools are named by the same resolver as the card.
    for pool in (_names.rows(_group_chats(_d._visible_items(db))), _names.rows(_known_chats(db))):
        hit = next((c for c in pool
                    if want in _norm_txt(c.get("name")) or _norm_txt(c.get("name")) in want), None)
        if hit is not None:
            return hit
    return None


def _thread_view(db: dict, active: dict, pending_here: list) -> list:
    """The open conversation, oldest first, in the shape widget.js already renders. A message that is STILL
    pending keeps its live fields — above all `n`, which is what the ✓/✕/🗄 buttons address; one that has been
    read (here or in the real app) arrives without them, so the widget shows it as history and offers no
    action on something already dealt with.

    Falls back to the pending items alone if there is no thread yet: an install that predates this, or a chat
    whose messages arrived before it existed, must still open."""
    platform, chat_id = active.get("platform"), active.get("chatId")
    try:
        from .. import thread
        msgs = thread.window(db, platform, chat_id)
    except Exception:  # noqa: BLE001
        msgs = []
    if not msgs:
        return list(pending_here)
    by_id = {str(it.get("messageId")): it for it in pending_here}
    out = []
    for m in msgs:
        live = by_id.pop(str(m.get("id")), None)
        row = {
            "platform": platform, "chatId": chat_id,
            "messageId": m.get("id"), "from": m.get("who") or "?",
            "body": m.get("body") or "", "ts": m.get("ts") or 0,
            "dir": m.get("dir") or "in", "read": bool(m.get("read")),
        }
        if m.get("mediaType"):
            row["mediaType"] = m.get("mediaType")
        if m.get("media"):
            row["media"] = m.get("media")
        # V2-680 — the envelope a MAIL is read by. These come off the THREAD, so a mail already read still
        # says who wrote it and who was copied: before this they were merged only from a still-pending
        # item, which means the fields vanished the moment the message was dealt with — exactly when the
        # operator scrolls back to check who else was on it.
        for k in ("subject", "senderId", "recipients"):
            if m.get(k):
                row[k] = m.get(k)
        if live is not None:
            for k in ("n", "urgencia", "dirigido_a_mi", "motivo", "senderId", "subject", "msgid", "group",
                      "recipients"):
                if live.get(k) is not None:
                    row[k] = live.get(k)
        out.append(row)
    # A pending item with no counterpart in the thread (arrived before threads existed, or was pruned) is still
    # the operator's mail — appended rather than dropped. Losing a real message to a bookkeeping gap is the one
    # outcome this whole file exists to prevent.
    for it in pending_here:
        if str(it.get("messageId")) in by_id:
            out.append(it)
    out.sort(key=lambda r: float(r.get("ts") or 0))
    return out


def _thread_meta(db: dict, active: dict) -> dict | None:
    """Where our copy of the conversation STARTS, so the widget can say it out loud instead of pretending the
    thread begins there. Carries `can_load_more` — the button only exists where asking makes sense."""
    from .. import data as _d
    try:
        from .. import thread
        info = thread.meta(db, active.get("platform"), active.get("chatId"))
    except Exception:  # noqa: BLE001
        return None
    info["platform"] = active.get("platform")
    info["supports_history"] = active.get("platform") in _d._HISTORY_PLATFORMS
    info["can_load_more"] = bool(info.get("can_load_more")) and info["supports_history"] and info["count"] > 0
    return info


def _peek_answer(payload: dict) -> dict:
    """A conversation handed WHOLE to the brain (V2-624) — «dame lo relevante del grupo del viaje», «resume
    esos correos». Read-only: the thread store already holds the segregated data, so analysis is a READ of it,
    never an index into memory. Newest messages win the budget (walking backwards), because the question is
    almost always about what is being said NOW; `load_more` first is the door to more past."""
    from .. import data as _d
    db = _d.load_db()
    hit = None
    name = str(payload.get("name") or payload.get("chat") or "").strip()
    if payload.get("platform") and payload.get("chatId") is not None:
        hit = {"platform": payload.get("platform"), "chatId": payload.get("chatId"), "name": ""}
    elif name:
        hit = _find_chat_by_name(db, name)
    elif db.get("active_chat"):
        hit = dict(db["active_chat"])
    if hit is None:
        return {"ok": False,
                "error": "no sé qué conversación leer — vuelve a llamar a peek con `name` (como aparece en la "
                         "lista) o con la conversación ya abierta"}
    from .. import thread as _th
    platform, chat_id = hit.get("platform"), hit.get("chatId")
    msgs = _th.window(db, platform, chat_id)
    if not msgs:
        return {"ok": False,
                "error": "no tengo mensajes guardados de esa conversación — si existe en la app real, "
                         "open + load_more los trae (o fetch_now para traer la actividad reciente del canal)"}
    try:
        limit = max(1, min(_PEEK_MAX_MSGS, int(payload.get("limit") or _PEEK_MAX_MSGS)))
    except (TypeError, ValueError):
        limit = _PEEK_MAX_MSGS
    rows, used = [], 0
    for m in reversed(msgs[-limit:]):
        body = (m.get("body") or "")[:_PEEK_MAX_BODY]
        if used + len(body) > _PEEK_BUDGET and rows:
            break
        used += len(body)
        rows.append({"from": m.get("who") or ("yo" if m.get("dir") == "out" else "?"),
                     "dir": m.get("dir") or "in", "ts": m.get("ts") or 0, "body": body})
    rows.reverse()
    info = _th.meta(db, platform, chat_id)
    return {"result": {
        "name": hit.get("name") or (info and "") or "",
        "platform": platform, "chatId": chat_id,
        "isGroup": bool(info.get("isGroup")), "held": len(msgs), "returned": len(rows),
        "complete": bool(info.get("complete")),
        "messages": rows,
        "note": "analiza/resume TÚ estos mensajes para contestar al operador — esto es la conversación tal "
                "cual; si necesita más pasado, open + load_more la amplía",
    }}
