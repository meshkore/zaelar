#
# views.py — the READ side of the messaging widget (V2-624): resolving a spoken chat name, the conversation
# view a thread renders from, the per-platform ACTIVITY criteria, `peek` (a conversation handed whole to the
# brain) and the autoresponder previews. Extracted from data.py when it crossed the architecture ratchet's
# unlisted-file cap — the ratchet is paid by EXTRACTING along a real seam, never by raising a ceiling.
#
# The seam is one-directional on purpose: data.py imports THIS module at the top; anything here that needs
# data.py's store or inbox helpers imports it LAZILY inside the function. Same widget-package contract as
# data.py itself: stdlib plus the `widgets` package — `connectors` only LAZILY and only because this
# widget sits in validator's curated _STDLIB_EXEMPT (V2-611: the email signature; V2-628: the archive).
#
import time
import unicodedata
from datetime import datetime

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
    from . import data as _d
    for pool in (_group_chats(_d._visible_items(db)), _known_chats(db)):
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
        from . import thread
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
        if live is not None:
            for k in ("n", "urgencia", "dirigido_a_mi", "motivo", "senderId", "subject", "msgid", "group"):
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
    from . import data as _d
    try:
        from . import thread
        info = thread.meta(db, active.get("platform"), active.get("chatId"))
    except Exception:  # noqa: BLE001
        return None
    info["platform"] = active.get("platform")
    info["supports_history"] = active.get("platform") in _d._HISTORY_PLATFORMS
    info["can_load_more"] = bool(info.get("can_load_more")) and info["supports_history"] and info["count"] > 0
    return info


def _criteria_for(db: dict, platform: str) -> dict | None:
    """The operator's persisted view criterion for one platform's lens (V2-624), or None (= the classic
    pending view, byte-for-byte what the lens always showed). Today one criterion exists: `window_h`,
    «conversations with activity in the last N hours»."""
    raw = (db.get("lens_criteria") or {}).get(platform)
    if not isinstance(raw, dict):
        return None
    try:
        win = float(raw.get("window_h") or 0)
    except (TypeError, ValueError):
        return None
    return {"window_h": win} if win > 0 else None


def _activity_chats(db: dict, platform: str, window_h: float) -> list:
    """Conversations of `platform` with activity inside the window, newest first — read whole from the THREAD
    store (V2-546's conversations), never from the pending inbox: «movimiento» includes what he already read
    and what he himself sent. No `n`: these rows are addressed by name (voice) or platform+chatId (a click),
    never by the chat-list numbering, which belongs to the pending inbox and would collide with it."""
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
    from . import data as _d
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


_ARCHIVE_MAX_ROWS = 20
_ARCHIVE_MAX_BODY = 200


def _search_archive_answer(payload: dict) -> dict:
    """The PERMANENT communications archive, answered as data (V2-628 F1). A question about PAST messages
    («when did the school write?», «did I ever answer it?») channels HERE — never to memory recall: the
    inbox, the threads and the msg pills all EXPIRE by design, and this log is the one copy that does not.
    Read-only; matches come back with their date so the model answers with names and dates. The answer also
    carries `archive_since`: the log only holds what arrived after its activation, and hiding that boundary
    is how «you have none» gets said over a period we simply never recorded (the V2-606 lesson)."""
    from connectors.messaging import archive
    from . import data as _d
    q = str(payload.get("q") or payload.get("text") or "").strip() or None
    sender = str(payload.get("sender") or payload.get("from") or "").strip() or None
    chat = str(payload.get("chat") or payload.get("group") or payload.get("name") or "").strip() or None
    platform = str(payload.get("platform") or "").strip().lower()
    platform = _d._PLAT_ALIASES.get(platform, platform) or None
    direction = payload.get("direction") if payload.get("direction") in ("in", "out") else None
    since = until = None
    for key, sign in (("since_days", "since"), ("until_days", "until")):
        try:
            days = float(payload.get(key))
        except (TypeError, ValueError):
            continue
        cut = time.time() - max(0.0, days) * 86400
        if sign == "since":
            since = cut
        else:
            until = cut
    if not any((q, sender, chat, platform, direction, since, until)):
        return {"ok": False,
                "error": "search_archive necesita algún criterio: `q` (texto), `sender`, `chat`, `platform`, "
                         "`since_days`, `until_days` o `direction`"}
    try:
        limit = max(1, min(_ARCHIVE_MAX_ROWS, int(payload.get("limit") or _ARCHIVE_MAX_ROWS)))
    except (TypeError, ValueError):
        limit = _ARCHIVE_MAX_ROWS
    rows = archive.search(q, sender=sender, chat=chat, platform=platform,
                          since=since, until=until, direction=direction, limit=limit)
    st = archive.stats()
    oldest = st.get("oldest")
    matches = []
    for r in rows:
        matches.append({
            "when": datetime.fromtimestamp(float(r.get("ts") or 0)).strftime("%Y-%m-%d %H:%M"),
            "platform": r.get("platform"), "dir": r.get("direction"),
            "chat": r.get("chat_name") or r.get("chat_id"),
            "from": "yo" if r.get("direction") == "out" else (r.get("sender") or "?"),
            "body": (r.get("body") or "")[:_ARCHIVE_MAX_BODY]})
    coverage = (datetime.fromtimestamp(float(oldest)).strftime("%Y-%m-%d") if oldest else None)
    if matches:
        detail = (f"{len(matches)} mensaje(s) del ARCHIVO permanente — contesta con nombres y fechas; "
                  f"el archivo cubre desde {coverage}")
    elif oldest is None:
        detail = ("el archivo está vacío todavía — guarda todo lo que llegue o salga desde su activación, "
                  "pero no indexa el pasado; para traer e indexar el pasado de UN chat concreto llama a "
                  "load_more con ese chat (o fetch_now con platform en telegram/email) y repite esta "
                  "búsqueda; si no, el buzón de la app real es la fuente")
    else:
        detail = (f"nada en el ARCHIVO casa con eso — cubre desde {coverage}; algo ANTERIOR a esa fecha no "
                  f"está guardado aquí (no se indexó el pasado), dilo en vez de afirmar que no existió. "
                  f"Para indexar el pasado de UN chat: load_more con ese chat (o fetch_now con platform en "
                  f"telegram/email) y repite esta búsqueda")
    result = {"matches": matches, "count": len(matches), "archive_since": coverage, "detail": detail}
    # F2 — the answered state: «¿lo llegamos a contestar?» is a JOIN, never a memory. On request, the
    # newest INBOUND match is checked for the first outgoing message in the same chat after its instant.
    if payload.get("check_reply") and rows:
        hit = next((r for r in rows if r.get("direction") == "in"), None)
        if hit is not None:
            rep = archive.replied(hit.get("platform"), hit.get("chat_id"), float(hit.get("ts") or 0))
            if rep:
                when = datetime.fromtimestamp(float(rep.get("ts") or 0)).strftime("%Y-%m-%d %H:%M")
                result["reply"] = {"when": when, "body": (rep.get("body") or "")[:_ARCHIVE_MAX_BODY]}
                result["detail"] += f"; SÍ se contestó — lo nuestro salió el {when}"
            else:
                result["reply"] = None
                result["detail"] += ("; NO consta ninguna respuesta nuestra posterior en ese chat "
                                     "(el archivo registra las salientes desde su activación)")
    return {"result": result}


def _chat_digest_answer(payload: dict) -> dict:
    """The per-chat digest (V2-628 F3) — «¿tengo que hacer alguna acción de este grupo?», «¿tengo algo
    pendiente de mis grupos?». Reads the LIVING state the idle pass distilled from the archive; with a chat
    named it returns that chat's digest, without one it returns every chat that still carries open actions.
    Read-only. A chat with no digest yet is said honestly — the pass runs while the chat is quiet, so a
    brand-new conversation has none; `peek` is the live read for that."""
    from connectors.messaging import digest as _dg
    chat = str(payload.get("chat") or payload.get("group") or payload.get("name") or "").strip() or None
    rows = _dg.find(chat, only_open=(chat is None))
    items = []
    for d in rows:
        items.append({
            "chat": d["chat_name"] or d["chat_id"], "platform": d["platform"],
            "summary": d["digest"].get("summary") or "",
            "open_actions": d["digest"].get("open_actions") or [],
            "deadlines": d["digest"].get("deadlines") or [],
            "updated": datetime.fromtimestamp(float(d["updated_ts"])).strftime("%Y-%m-%d %H:%M")})
    if items:
        detail = ("estado destilado del ARCHIVO por chat — contesta nombrando las acciones abiertas y sus "
                  "fechas; si open_actions está vacío, di que no hay nada pendiente de ese chat")
    elif chat:
        detail = (f"no hay digest de «{chat}» todavía — se destila en reposo cuando el chat tiene mensajes "
                  "nuevos; para leerlo AHORA usa peek con ese nombre, no digas que no hay nada pendiente")
    else:
        detail = "ningún chat con acciones abiertas registradas en los digests"
    return {"result": {"digests": items, "count": len(items), "detail": detail}}


def _peek_answer(payload: dict) -> dict:
    """A conversation handed WHOLE to the brain (V2-624) — «dame lo relevante del grupo del viaje», «resume
    esos correos». Read-only: the thread store already holds the segregated data, so analysis is a READ of it,
    never an index into memory. Newest messages win the budget (walking backwards), because the question is
    almost always about what is being said NOW; `load_more` first is the door to more past."""
    from . import data as _d
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
    from . import thread as _th
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


def _autoresponder_preview(payload: dict) -> dict | None:
    """Validation + preview for set_autoresponder on the backed route — computed on a COPY, because this hook
    must never write (the owner persists). The ack the model sees has to say what WILL be active."""
    from . import autorespond, data as _d
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
        from . import autorespond, data as _d
        raw = db.get("autoresponder") or {}
        return {p: autorespond.config_for(db, p) for p in _d._PLATFORMS if p in raw}
    except Exception:
        return {}


def _group_chats(items: list) -> list:
    """Group the flat, already renumbered list by (platform, chatId), preserving appearance order: one item per
    chat instead of one per message. Each chat has its own `n`, a separate addressing space from `items`
    ([[msg.open:N]]/[[msg.readchat:N]] use this; [[msg.read:N]]/[[msg.dismiss:N]] still use the `items` `n`, only
    addressable when the chat is open)."""
    from . import data as _d
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


# ── Reading what the CALLER referred to, and what the card must show about policy (moved here V2-626) ──────
# Both are read-side shaping that stayed behind in data.py; they moved when data.py crossed the unlisted-file
# cap again. Same rule as the V2-624 extraction: the ratchet is paid by moving code along the seam that is
# already there, never by raising a ceiling.

def _open_ref(payload: dict) -> tuple:
    """(n, name) normalized for open. widget_data's item convention drops a natural reference into the
    action's primary payload key, so `n` can arrive as "1" (coerce) or as a NAME (reroute) — without this,
    `widget_data(open, item='Francisco')` missed every chat while the list sat on screen (V2-544)."""
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
    from .policy import policy_for
    from . import data as _d          # `_PLATFORMS` lives with the store shape, not with the views
    return {p: policy_for(db, p) for p in _d._PLATFORMS}
