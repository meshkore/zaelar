#
# views/chats.py — the read side of the chat LISTS: the per-platform activity criteria and their rows, the grouped
# inbox, the open reference, the effective notify policy and the autoresponder previews. Same one-directional seam
# as the rest of `views/`: anything that needs data.py imports it LAZILY inside the function.
#
import time


def _criteria_for(db: dict, platform: str) -> dict | None:
    """His persisted view criterion for one platform's lens (V2-624), or None (= the pending view). One criterion
    exists: `window_h`, «conversations with activity in the last N hours»."""
    raw = (db.get("lens_criteria") or {}).get(platform)
    if not isinstance(raw, dict):
        return None
    try:
        win = float(raw.get("window_h") or 0)
    except (TypeError, ValueError):
        return None
    return {"window_h": win} if win > 0 else None


def _activity_chats(db: dict, platform: str, window_h: float) -> list:
    """Conversations of `platform` with activity inside the window, newest first, read from the THREAD store (what
    he read and sent count). No `n`: addressed by name or platform+chatId, never the pending inbox's numbering."""
    cutoff = time.time() - float(window_h) * 3600
    out = []
    for k, th in (db.get("threads") or {}).items():
        plat, _, chat_id = str(k).partition("|")
        if plat != platform or not chat_id or not isinstance(th, dict):
            continue
        msgs = th.get("msgs") or []
        if not msgs:
            continue
        last = msgs[-1]
        last_ts = float(last.get("ts") or 0)
        if last_ts < cutoff:
            continue
        name = th.get("name") or next((m.get("who") for m in msgs
                                       if m.get("dir") == "in" and m.get("who")), chat_id)
        out.append({
            "platform": plat, "chatId": chat_id, "name": name, "isGroup": bool(th.get("isGroup")),
            "lastTs": last_ts, "lastFrom": last.get("who") or "",
            "lastBody": (last.get("body") or "")[:160], "lastMediaType": last.get("mediaType", ""),
            "inWindow": sum(1 for m in msgs if float(m.get("ts") or 0) >= cutoff),
            "unread": sum(1 for m in msgs if m.get("dir") == "in" and not m.get("read")),
        })
    out.sort(key=lambda c: -c["lastTs"])
    return out


def _activity_answer(db: dict, platform: str) -> dict:
    """The activity-view half of a `show_view` answer, {} when that platform has no criterion set. Carries the
    rows so the turn answers with NAMES, and names `fetch_now` when the local window looks thin — the lens
    shows what the store holds; the fetch is the door that fills it."""
    from .. import data as _d
    crit = _criteria_for(db, platform) if platform else None
    if not crit:
        return {}
    rows = _activity_chats(db, platform, crit["window_h"])
    out = {"criteria": {"window_h": crit["window_h"]}, "activity_count": len(rows),
           "activity": [{"name": r["name"], "isGroup": r["isGroup"], "unread": r["unread"],
                         "inWindow": r["inWindow"]} for r in rows[:12]]}
    if platform in _d._FETCH_PLATFORMS and len(rows) < 3:
        out["detail"] = (f"solo tengo {len(rows)} conversación(es) guardadas en esa ventana — "
                         f"fetch_now {{platform:'{platform}'}} le pide al conector la actividad real del período")
    return out


def _autoresponder_preview(payload: dict) -> dict | None:
    """Validation + preview for set_autoresponder on the backed route — computed on a COPY, because this hook
    must never write (the owner persists). The ack the model sees has to say what WILL be active."""
    from .. import autorespond, data as _d
    raw = str(payload.get("platform") or "all").strip().lower()
    plats = list(_d._PLATFORMS) if raw in ("all", "todas", "todos", "") \
        else [_d._PLAT_ALIASES.get(raw, raw)]
    if any(p not in _d._PLATFORMS for p in plats):
        return {"ok": False,
                "error": "set_autoresponder necesita `platform`: 'whatsapp', 'telegram', 'email' o 'all'"}
    db = _d.load_db()
    text = payload.get("text")
    if payload.get("enabled") and not str(text or "").strip() and \
            not any(autorespond.config_for(db, p)["text"] for p in plats):
        return {"ok": False,
                "error": "no hay ningún mensaje que responder — pásame `text` con lo que debe contestar"}
    preview = {}
    try:
        for p in plats:
            scratch = {"autoresponder": {k: dict(v) for k, v in (db.get("autoresponder") or {}).items()
                                         if isinstance(v, dict)}}
            preview[p] = autorespond.set_config(scratch, p, text=text, hours=payload.get("hours"),
                                                enabled=payload.get("enabled"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"result": {"autoresponder": preview,
                       "detail": "queda configurado; responde una sola vez por chat cada 24 h, nunca en "
                                 "grupos, y en email solo a correos dirigidos a él"}}


def _autoresponder_view(db: dict) -> dict:
    try:
        from .. import autorespond, data as _d
        raw = db.get("autoresponder") or {}
        return {p: autorespond.config_for(db, p) for p in _d._PLATFORMS if p in raw}
    except Exception:
        return {}


def _group_chats(items: list) -> list:
    """Group the flat, already renumbered list by (platform, chatId), preserving appearance order: one item per
    chat instead of one per message. Each chat has its own `n`, a separate addressing space from `items`
    ([[msg.open:N]]/[[msg.readchat:N]] use this; [[msg.read:N]]/[[msg.dismiss:N]] still use the `items` `n`, only
    addressable when the chat is open)."""
    from .. import data as _d
    order, by_key = [], {}
    for it in items:
        key = (it.get("platform"), str(it.get("chatId")))
        g = by_key.get(key)
        if g is None:
            g = {"platform": it.get("platform"), "chatId": it.get("chatId"),
                 "name": it.get("group") or it.get("from") or "?", "isGroup": bool(it.get("isGroup")),
                 "count": 0, "rank": 3, "dirigido_a_mi": False, "highlight": False, "last": it}
            by_key[key] = g
            order.append(key)
        g["count"] += 1
        g["rank"] = min(g["rank"], _d._URG_RANK.get(it.get("urgencia"), 3))
        g["dirigido_a_mi"] = g["dirigido_a_mi"] or bool(it.get("dirigido_a_mi"))
        # A chat belongs in the summary as soon as ONE of its messages does — the alternative silently buries a
        # message addressed to him under a chat whose other traffic is noise (V2-607).
        g["highlight"] = g["highlight"] or bool(it.get("highlight"))
        g["last"] = it   # most recent by appearance order; the store has no timestamp
    rank_to_urg = {0: "alta", 1: "media", 2: "baja"}
    chats = []
    for i, key in enumerate(order, 1):
        g = by_key[key]
        last = g["last"]
        chats.append({
            "n": i, "platform": g["platform"], "chatId": g["chatId"], "name": g["name"],
            "isGroup": g["isGroup"], "count": g["count"], "dirigido_a_mi": g["dirigido_a_mi"],
            "highlight": g["highlight"],
            "urgencia": rank_to_urg.get(g["rank"], "media"),
            "lastFrom": last.get("from"), "lastBody": last.get("body", ""), "lastMotivo": last.get("motivo", ""),
            # V2-543: real time + media class of the preview (0/"" for legacy rows without them).
            "lastTs": last.get("ts", 0), "lastMediaType": last.get("mediaType", ""),
        })
    return chats


# ── Reading what the CALLER referred to, and what the card must show about policy ──────────────────────────

def _open_ref(payload: dict) -> tuple:
    """(n, name) normalized for open: widget_data drops a natural reference into the primary key, so `n` can
    arrive as "1" (coerced) or as a NAME (rerouted) (V2-544)."""
    n = payload.get("n")
    name = str(payload.get("name") or payload.get("chat") or "").strip()
    if isinstance(n, str):
        n = n.strip()
        if n.isdigit():
            n = int(n)
        else:
            name, n = (name or n), None
    return n, name


def _notify_policy_view(db: dict) -> dict:
    """Effective (normalized) notification policy per platform, for the card and for read_widget. Always the
    full platform set, so a reader never has to guess what an absent entry means."""
    from ..policy import policy_for
    from .. import data as _d          # `_PLATFORMS` lives with the store shape, not with the views
    return {p: policy_for(db, p) for p in _d._PLATFORMS}
