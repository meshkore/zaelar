"""The messaging card's ANSWERING actions — the ops that return data and never write (V2-778 F1, 2026-10-01).

Moved out of `widgets/mensajeria/data.py` (1,070 lines, over the 900 a new file may reach): `answer_action` (the
digest of a chat, the archive search, the fetch window…), unchanged, reading every name of `data` through the
module (`_d.<name>`) so a patch on `data` still governs it. `data.answer_action` resolves here — the door
`widgets/server_api` and the tests call.
"""
from __future__ import annotations

from widgets.mensajeria import data as _d


def answer_action(action: str, payload: dict | None = None) -> dict | None:
    """READ-ONLY answer/validation for the backed route (V2-543). The owner's mailbox keeps one writer but
    swallowed every return: `show_view`'s answer (the matching chats) and the teach-the-shape errors never
    reached the brain — the screen moved by SSE while the turn got a bare `{"queued": true}`. This computes
    the ANSWER and vetoes an invalid order without touching the store; the mutation still goes through the
    owner. Must never call store.save."""
    payload = payload or {}
    if action in ("send_to", "forward"):
        # V2-683 — the veto runs BEFORE the order reaches the owner's mailbox: an unresolvable recipient must
        # never be queued and then fail out of sight, and the sentence that says what is missing is the only
        # thing that makes the next attempt succeed.
        if action == "forward":
            # full21 E3: `forward {contact: Quinn}` with no note was refused by `resolve_target` in words that named
            # `send_to` — another action — so the same-turn correction retried the wrong one and nothing went out.
            if not str(payload.get("text") or "").strip():
                return {"ok": False, "error": "falta `text` en forward: la nota para esa persona con lo que el "
                                              "operador quiere decirle — vuelve a llamar a forward con contact, "
                                              "text y from"}
            payload = {**payload, "contact": payload.get("contact") or payload.get("to"), "channel": "email"}
            if (no_files := _d._outbound.forward_without_files(_d.load_db(), payload)):
                return no_files
        t = _d._outbound.resolve_target(payload)
        if not t.get("ok"):
            return t
        return {"ok": True, "result": {"to": t.get("name"), "channel": t.get("platform")}}
    if action == "show_view":
        raw = str(payload.get("platform") or payload.get("view") or "").strip().lower()
        if raw not in _d._PLAT_ALIASES:
            return {"ok": False,
                    "error": "no reconozco esa vista — vuelve a llamar a show_view con `platform`: 'all' "
                             "(la lista principal unificada), 'whatsapp', 'telegram' o 'email'"}
        platform = _d._PLAT_ALIASES[raw]
        db = _d.load_db()
        chats = [c for c in _d._group_chats(_d._visible_items(db))
                 if not platform or c.get("platform") == platform]
        result = {"platform": platform or "all", "count": len(chats),
                  "chats": [{"n": c.get("n"), "name": c.get("name"), "platform": c.get("platform"),
                             "count": c.get("count")} for c in chats[:12]]}
        # V2-624 — PREVIEW of the criterion the owner is about to persist (this hook must never write): with
        # `window_h` in the order, answer with the activity rows that window yields RIGHT NOW; without it,
        # with whatever criterion is already set.
        if platform and "window_h" in payload:
            try:
                win = float(payload.get("window_h") or 0)
            except (TypeError, ValueError):
                return {"ok": False,
                        "error": "window_h tiene que ser un número de HORAS (72 = últimos 3 días); "
                                 "0 quita el criterio y vuelve a la vista de pendientes"}
            if win > 0:
                rows = _d._activity_chats(db, platform, min(win, _d._WINDOW_MAX_H))
                result.update({"criteria": {"window_h": min(win, _d._WINDOW_MAX_H)},
                               "activity_count": len(rows),
                               "activity": [{"name": r["name"], "isGroup": r["isGroup"],
                                             "unread": r["unread"], "inWindow": r["inWindow"]}
                                            for r in rows[:12]]})
                if platform in _d._FETCH_PLATFORMS and len(rows) < 3:
                    result["detail"] = (f"solo tengo {len(rows)} conversación(es) guardadas en esa ventana — "
                                        f"fetch_now {{platform:'{platform}'}} trae del conector la actividad "
                                        f"real del período")
        else:
            result.update(_d._activity_answer(db, platform))
        return {"result": result}
    if action == "fetch_now":
        raw = str(payload.get("platform") or "").strip().lower()
        platform = _d._PLAT_ALIASES.get(raw, raw)
        if platform not in _d._FETCH_PLATFORMS:
            if platform == "whatsapp":
                return {"ok": False,
                        "error": ("WhatsApp no permite pedirle al teléfono las conversaciones en bloque: lo "
                                  "nuevo llega solo en tiempo real, y de un chat CONCRETO que ya tengamos sí "
                                  "puedo traer mensajes anteriores (open + load_more)")}
            return {"ok": False,
                    "error": "fetch_now necesita `platform`: 'telegram' o 'email'"}
        try:
            since = float(payload.get("since_hours") or _d._FETCH_DEFAULT_H)
        except (TypeError, ValueError):
            since = _d._FETCH_DEFAULT_H
        since = max(1.0, min(since, _d._WINDOW_MAX_H))
        return {"result": {"asked": True, "platform": platform, "since_hours": since,
                           "detail": "pedido al conector — las conversaciones de ese período irán apareciendo "
                                     "en unos segundos; vuelve a mirar (show_view o peek) cuando lleguen"}}
    if action == "peek":
        return _d._peek_answer(payload)
    if action == "search_archive":
        return _d._search_archive_answer(payload)
    if action == "chat_digest":
        return _d._chat_digest_answer(payload)
    if action == "set_autoresponder":
        return _d._autoresponder_preview(payload)
    if action == "clear_autoresponder":
        return {"result": {"cleared": True,
                           "detail": "autorespondedor apagado y borrado — confírmaselo al operador"}}
    if action == "open":
        n, name = _d._open_ref(payload)
        if n is None and not name:
            return None
        db = _d.load_db()
        hit = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None) \
            if n is not None else _d._find_chat_by_name(db, name)
        if hit is None:
            return {"ok": False,
                    "error": "no encuentro ese chat — vuelve a llamar a open con el `n` de la lista o con "
                             "`name` tal como aparece en ella"}
        return {"result": {"opened": hit.get("name"), "platform": hit.get("platform")}}
    if action == "load_more":
        db = _d.load_db()
        chat = db.get("active_chat")
        if payload.get("platform") and payload.get("chatId") is not None:
            chat = {"platform": payload.get("platform"), "chatId": payload.get("chatId")}
        if not chat:
            return {"ok": False,
                    "error": "no hay ninguna conversación abierta — abre primero el chat con open y vuelve a "
                             "llamar a load_more"}
        if chat.get("platform") not in _d._HISTORY_PLATFORMS:
            return {"ok": False,
                    "error": f"traer mensajes anteriores no está soportado para {chat.get('platform')} todavía"}
        if (_d._thread_meta(db, chat) or {}).get("complete"):
            return {"result": {"loaded": 0, "complete": True,
                               "detail": "ya tienes el principio de esta conversación"}}
        return {"result": {"asked": True, "platform": chat.get("platform"),
                           "detail": "se los he pedido a la app; aparecerán arriba en cuanto lleguen"}}
    if action in ("archive", "trash"):
        n = payload.get("n")
        mid = payload.get("messageId")
        items = _d._visible_items(_d.load_db())
        hit = next((it for it in items
                    if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
        if hit is None:
            return {"ok": False,
                    "error": f"no encuentro ese mensaje — vuelve a llamar a {action} con el `n` de la lista"}
        if hit.get("platform") != "email":
            return {"ok": False,
                    "error": ("archivar/borrar en la app real solo está soportado para EMAIL hoy — para "
                              "WhatsApp/Telegram usa read (marcar leído) o dismiss (descartar del widget)")}
        return {"result": {"action": action, "from": hit.get("from"), "subject": hit.get("subject", "")}}
    return None
