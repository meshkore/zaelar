#
# views/archive.py — the PERMANENT communications archive, read: the rows a search asks for, the real mailbox asked
# for what the index never saw, the free-text read seam, and the search/digest answers. The names a test patches
# (`archive_rows`, `mailbox_fill`, `_unknown_terms`) are called back through the `views` facade, so a patch there
# still governs every caller here.
#
import re
import time
from datetime import datetime


_ARCHIVE_MAX_ROWS = 20
_ARCHIVE_MAX_BODY = 200


def archive_rows(payload: dict) -> list:
    """The archive rows a `search_archive` payload asks for (newest first); [] without any criterion."""
    from connectors.messaging import archive
    from .. import data as _d
    q = str(payload.get("q") or payload.get("query") or payload.get("text") or "").strip() or None
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
        return []
    try:
        limit = max(1, min(_ARCHIVE_MAX_ROWS, int(payload.get("limit") or _ARCHIVE_MAX_ROWS)))
    except (TypeError, ValueError):
        limit = _ARCHIVE_MAX_ROWS
    rows = archive.search(q, sender=sender, chat=chat, platform=platform,
                          since=since, until=until, direction=direction, limit=limit)
    return _named_sender_first(rows, q, sender, chat, platform, since, until, direction, limit)


def _named_sender_first(rows, q, sender, chat, platform, since, until, direction, limit) -> list:
    """A `q` that NAMES a sender puts that sender's own messages first, ahead of newer mail that merely mentions
    it (our own forwards). Which word is a sender is read from the archive (`archive._naming_terms`), any language."""
    from connectors.messaging import archive
    if not q or sender or chat:
        return rows
    try:
        named = archive._naming_terms(archive._conn(), _WORD_RE.findall(q.lower()))
    except Exception:  # noqa: BLE001
        return rows
    if not named:
        return rows
    first, seen = [], set()
    for t in named:
        for r in archive.search(None, sender=t, platform=platform, since=since, until=until,
                                direction=direction, limit=limit):
            if r["id"] not in seen:
                seen.add(r["id"]); first.append(r)
    return (first + [r for r in rows if r["id"] not in seen])[:limit]


_WORD_RE = re.compile(r"\w{3,}", re.UNICODE)
_MAILBOX_MAX_TERMS = 5
_MAILBOX_MAX_HITS = 5
_MAILBOX_ASKED_TTL = 600.0
_MAILBOX_ASKED: dict = {}   # term → when it was last asked of the mailbox: a filler word costs one SEARCH, not one per turn


def mailbox_fill(terms) -> int:
    """Ask the REAL mailbox for mail whose sender or subject holds any of `terms`, and INDEX what it returns in the
    permanent archive. Returns how many rows were new. Never raises; 0 when email is not connected.

    The archive is the index, the mailbox the source: a question the index cannot answer is asked of the source and
    the answer indexed on the way back. Read-only on the mailbox side (BODY.PEEK, folder opened read-only)."""
    now = time.time()
    terms = [t for t in (str(x).strip().lower() for x in (terms or []))
             if t and now - _MAILBOX_ASKED.get(t, 0.0) > _MAILBOX_ASKED_TTL][:_MAILBOX_MAX_TERMS]
    if not terms:
        return 0
    for t in terms:
        _MAILBOX_ASKED[t] = now
    try:
        from connectors.email import config as _ecfg
        mb = _ecfg.mailbox()
        if mb is None:
            return 0
        from connectors.email.search import search_text
        msgs = search_text(mb, terms, limit=_MAILBOX_MAX_HITS)
    except Exception:  # noqa: BLE001
        return 0
    from connectors.messaging import archive
    n = 0
    for m in msgs or []:
        if not isinstance(m, dict) or not m.get("chatId"):
            continue
        n += archive.record("email", m["chatId"], [m], direction="in", chat_name=str(m.get("senderName") or ""))
    return n


def _unknown_terms(text: str) -> list[str]:
    """The words of a question the archive has NEVER seen — the ones that carry news (a sender, a product, an
    invoice number). A word the archive already holds adds nothing the local search did not already weigh."""
    from connectors.messaging import archive
    out: list[str] = []
    for w in dict.fromkeys(_WORD_RE.findall(str(text or "").lower())):
        if archive.doc_count(w) == 0:
            out.append(w)
    return out


def read_query_answer(question: str) -> str:
    """The archive's rows a free-text question is about, best first — the `read_query` seam of `widget_read`.

    Resolved against the permanent archive, never the card's summary (BM25, so the rare word naming the sender
    outranks the filler); words the archive never saw are asked of the real mailbox first and indexed. "" when
    nothing matches: the summary then answers, marked as a summary."""
    from connectors.messaging import archive
    words = list(dict.fromkeys(_WORD_RE.findall(str(question or "").lower())))
    if not words:
        return ""
    unknown = _f._unknown_terms(question)
    filled = bool(unknown and _f.mailbox_fill(unknown))
    # …and the card brings what was found INTO its conversation through its one writer (`search_archive` →
    # _bring_back_found_mail), since «open it» and a forward act on the card. A sender the question names is
    # brought back whether the archive or the mailbox found it.
    try:
        from widgets import supervisor as _sup
        named = archive._naming_terms(archive._conn(), words)
        for t in dict.fromkeys((unknown if filled else []) + named):
            if archive.search(t, platform="email", limit=1):
                _sup.enqueue_from_thread("mensajeria", "search_archive", {"q": t, "platform": "email"})
    except Exception:  # noqa: BLE001
        pass
    rows = archive.ranked(words, limit=8)
    if not rows:
        return ""
    from nucleo import untrusted as _u          # V2-778 F4-32: what others wrote is fenced as DATA; ours is not
    lines = ["Del ARCHIVO permanente de comunicaciones (y del buzón real para lo que no estaba indexado), lo más "
             "relevante primero. " + _u.NOTE]
    for r in rows:
        when = datetime.fromtimestamp(float(r.get("ts") or 0)).strftime("%Y-%m-%d %H:%M")
        ours = r.get("direction") == "out"
        who = "yo" if ours else _u.neutralize(r.get("sender") or r.get("chat_name") or "?")
        body = " ".join(str(r.get("body") or "").split())[:240]
        lines.append(f"· {when} · {r.get('platform')} · {who} <{r.get('chat_id')}> · "
                     f"{body if ours else _u.inline(body)}")
    return "\n".join(lines)


def _search_archive_answer(payload: dict) -> dict:
    """The PERMANENT communications archive, answered as data (V2-628). A question about PAST messages comes HERE,
    never to memory recall: inbox, threads and msg pills expire, this log does not. Read-only, dated matches. It
    carries `archive_since`, so «you have none» is never said over a period that was never recorded."""
    from connectors.messaging import archive
    from .. import data as _d
    q = str(payload.get("q") or payload.get("query") or payload.get("text") or "").strip() or None
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
    rows = _f.archive_rows(payload)
    if not rows and (q or sender) and platform in (None, "email"):
        # Nothing indexed: ask the real mailbox, index what it returns, and look again.
        if _f.mailbox_fill(([sender] if sender else []) + (_WORD_RE.findall(q.lower()) if q else [])):
            rows = _f.archive_rows(payload)
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
    # How each platform's PAST reaches the archive (connectors/messaging/history.py): WhatsApp and Telegram are
    # walked back once, the mailbox is asked on demand. Without it, «nothing found» over a walk still running
    # reads as «it never happened».
    try:
        from connectors.messaging import history as _history
        result["history"] = _history.coverage()
        walking = [f"{p}: {c.get('done', 0)} de {c.get('started', 0)} chats ya completos"
                   for p, c in result["history"].items() if c.get("mode") == "walk"]
        if not matches and walking:
            result["detail"] += ("; el historial de " + ", ".join(walking) + " (se sigue bajando en segundo "
                                 "plano); el correo no se copia: se busca en el buzón cuando hace falta")
    except Exception as e:  # noqa: BLE001 — the coverage line is a courtesy, never a reason to fail the answer
        import logging
        logging.getLogger("zaelar.mensajeria.views").warning(f"archive coverage unavailable: {type(e).__name__}")
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
    """The per-chat digest (V2-628): the state the idle pass distilled from the archive — that chat's digest, or
    every chat with open actions. Read-only. A chat with no digest yet is said honestly (`peek` is the live read)."""
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


from .. import views as _f  # noqa: E402 — the facade: a patch on `views.<name>` governs the calls above
