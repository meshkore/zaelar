"""widgets/mensajeria/outbound/targets.py — WHO a send goes to: the conversation a reply answers, the person a new
message is for (resolved through `widgets/directory.py`, refused when in doubt), and the one message he points at.
"""
from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")

#: Kept in step with `widgets/directory.PLATFORMS` — this widget's three channels.
PLATFORMS = ("whatsapp", "telegram", "email")

_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "correo"}


def label(platform: str) -> str:
    return _LABEL.get(str(platform or "").strip().lower(), str(platform or ""))


def _directory():
    from widgets import directory
    return directory


# ── ANSWERING a conversation ───────────────────────────────────────────────────────────────────────────
# One direction only, the `views` contract: data.py imports this at the top, and the store-shape helpers these
# need (`_renumber`, `_key`) are read back LAZILY.

def resolve_reply_target(db: dict, n=None, mid: str | None = None) -> dict | None:
    """The identity `draft`/`send_draft` reply to (V2-611); `reply` keeps its own resolution.

    `n`/`messageId` resolve against the flat renumbered list (an ITEM, as in read/dismiss/archive/trash/hide, never
    a `_group_chats` row). With NEITHER and a thread open, it is the conversation itself: «the person I'm talking
    to», not a specific past message."""
    from .. import data as _d
    if n is not None or mid:
        # Renumber first: a stored item carries no `n` until `_renumber` assigns it, so a bare `n` would never resolve.
        items = _d._renumber(db.get("items", []))
        return next((it for it in items
                     if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
    active = db.get("active_chat")
    if active is None:
        return None
    key = (active.get("platform"), str(active.get("chatId")))
    msgs = [it for it in db.get("items", []) if (it.get("platform"), str(it.get("chatId"))) == key]
    if msgs:
        return msgs[-1]
    # Nothing pending in this thread, but the conversation still has an identity to reply to: answering never
    # requires an unread message (V2-546). `enqueue_reply` reads only platform/chatId/senderId from this shape.
    return {"platform": key[0], "chatId": key[1]}


def _resolve_recipient(who: str):
    """Resolve a recipient reference to its directory contacts, tolerating the DECORATION the model appends.

    «Name (Telegram @handle)»: the name is the durable part, the parenthetical and trailing clauses are decoration,
    peeled through the ONE shared matcher (`widgets/textmatch.spans`, V2-705). The FIRST span that resolves wins,
    returned verbatim — several contacts are still the answer (the caller asks which), never silently the first."""
    from ... import textmatch
    d = _directory()
    for span in textmatch.spans(who):
        hits = d.resolve(span, tolerant=False)
        if hits:
            return hits
    return []


def _near_recipient(who: str) -> list[dict]:
    """The contacts only a spelling-tolerant match finds — never written to, named back as a question: «¿te refieres
    a Cryptonite?» costs one turn; the wrong person costs what cannot be taken back."""
    from ... import textmatch
    d = _directory()
    for span in textmatch.spans(who):
        hits = d.near(span)
        if hits:
            return hits
    return []


def _one_mailbox(hits: list[dict], want: str, d) -> list[dict]:
    """Several contacts that all reach the SAME place are one recipient — [the first] — else [].

    Asking which cannot change where the mail goes. Two contacts with DIFFERENT channels stay an ambiguity."""
    keys = set()
    for c in hits:
        ch = d.channel_for(c, want)
        if not ch:
            return []
        keys.add((str(ch.get("platform") or ""), str(ch.get("handle") or ch.get("chatId") or "").strip().lower()))
    return [hits[0]] if len(keys) == 1 else []


def resolve_target(payload: dict | None = None) -> dict:
    """WHO this is going to and HOW. Returns `{"ok": True, ...}` with the target, or `{"ok": False, "error"}`
    carrying a sentence that says what is missing — never a guess, never the first of several matches."""
    payload = payload or {}
    text = str(payload.get("text") or "").strip()
    who = str(payload.get("contact") or payload.get("to") or "").strip()
    want = str(payload.get("channel") or payload.get("platform") or "").strip().lower()
    if want and want not in PLATFORMS:
        return {"ok": False, "error": f"no reconozco el canal «{want}» — send_to admite whatsapp, telegram "
                                      f"o email"}
    if not text and not payload.get("files") and "attach_from" not in payload:   # a photo alone is a message
        return {"ok": False, "error": "no me ha llegado el mensaje — vuelve a llamar a send_to con `text` "
                                      "(lo que hay que decirle), sin volver a preguntárselo al operador si "
                                      "ya te lo dijo"}
    if not who:
        return {"ok": False, "error": "no me ha llegado a quién — vuelve a llamar a send_to con `contact` "
                                      "(el nombre tal y como lo dijo el operador)"}

    hits = _resolve_recipient(who)
    d = _directory()
    if len(hits) > 1:
        hits = _one_mailbox(hits, want, d) or hits
    if len(hits) > 1:
        names = " · ".join(f"{c.get('name')}" + (f" ({c.get('city')})" if c.get("city") else "")
                           for c in hits[:5])
        # The ambiguity is the answer: asking which one costs a turn, writing to the wrong person costs
        # something that cannot be taken back (the `refs.py` doctrine, at the one door where it is final).
        return {"ok": False, "say": "widgets.mensajeria.refusal_which_person", "error": f"tengo {len(hits)} contactos que encajan con «{who}»: {names}. "
                                      f"PREGÚNTALE al operador a cuál se refiere y vuelve a llamar a send_to "
                                      f"con el nombre completo."}
    if not hits:
        # No contact — an ADDRESS said out loud is still a complete way to reach somebody.
        if _EMAIL_RE.match(who) and want in ("", "email"):
            return {"ok": True, "platform": "email", "to": who, "chatId": who, "name": who,
                    "contactId": "", "known": False}
        near = _near_recipient(who)
        if near:
            names = " · ".join(str(c.get("name") or "") for c in near[:3])
            return {"ok": False, "near": [c.get("name") for c in near[:3]], "say": "widgets.mensajeria.refusal_near_name",
                    "error": f"no tengo a nadie que se llame exactamente «{who}»; el más parecido es {names}. "
                               f"PREGÚNTALE al operador si es ese y vuelve a llamar con el nombre exacto — "
                               f"nunca se escribe a alguien por parecido."}
        return {"ok": False, "say": "widgets.mensajeria.refusal_unknown_person", "error": f"no tengo a «{who}» en el directorio. Si el operador te ha dado su "
                                      f"teléfono, su usuario o su correo, guárdalo primero con "
                                      f"contactos/add_contact (o set_channel) y vuelve a intentarlo; si no, "
                                      f"pregúntaselo."}

    c = hits[0]
    ch = d.channel_for(c, want)
    if not ch:
        have = [str(x.get("platform")) for x in d.channels(c)]
        name = c.get("name") or who
        if want:
            tail = (f"lo que sí tengo suyo es {', '.join(label(p) for p in have)}"
                    if have else "no tengo ningún canal suyo")
            return {"ok": False, "say": "widgets.mensajeria.refusal_no_channel", "error": f"no tengo el {label(want)} de {name} — {tail}. Pregúntale al "
                                          f"operador el dato que falta y guárdalo con contactos/set_channel."}
        if have:
            return {"ok": False, "say": "widgets.mensajeria.refusal_which_channel", "error": f"{name} tiene varios canales ({', '.join(label(p) for p in have)}) "
                                          f"y ninguno marcado como preferido. PREGÚNTALE al operador por cuál "
                                          f"le escribe y vuelve a llamar a send_to con `channel`."}
        return {"ok": False, "say": "widgets.mensajeria.refusal_no_channel", "error": f"no tengo ninguna forma de escribir a {name}: ni teléfono, ni usuario "
                                      f"de Telegram, ni correo. Pregúntaselo al operador y guárdalo con "
                                      f"contactos/set_channel."}

    return {"ok": True, "platform": ch["platform"], "to": str(ch.get("handle") or ch.get("chatId") or ""),
            "chatId": str(ch.get("chatId") or ""), "name": c.get("name") or who,
            "contactId": c.get("id") or "", "known": True}


def describe(payload: dict | None = None) -> dict:
    """What the CONFIRMATION needs to say, resolved read-only. `{"ok": False}` keeps its sentence so the
    caller can decide whether to ask at all; the wording itself lives in the confirm gate."""
    t = resolve_target(payload)
    if not t.get("ok"):
        return t
    p = payload or {}
    return {**t, "text": str(p.get("text") or "").strip(),
            "subject": str(p.get("subject") or "").strip(),
            "objective": str(p.get("objective") or "").strip()}


def _message_ref(db: dict, ref: dict) -> dict | None:
    """ONE message the operator points at: `n` of the list on screen, a `messageId`, or — with neither — the
    last message received in the conversation that is OPEN (what «this email» means). Its item or thread row."""
    from .. import data as _d, thread as _th
    ref = ref if isinstance(ref, dict) else {}
    n, mid = ref.get("n"), str(ref.get("messageId") or "").strip()
    who = str(ref.get("from") or "").strip().lower()
    if who:
        # BY WHO SENT IT or WHAT IT IS ABOUT («the Inworld one») — the list on screen first, then every
        # conversation this card keeps, so the model never has to guess an `n`.
        def _hit(m) -> bool:
            hay = " ".join(str(m.get(k) or "") for k in ("from", "who", "senderId", "subject", "chatId")).lower()
            return who in hay
        for it in _d._visible_items(db):
            if _hit(it):
                return it
        best = None
        for tkey, th in (db.get("threads") or {}).items():
            plat, _, chat = str(tkey).partition("|")
            for m in (th or {}).get("msgs") or []:
                if m.get("dir") == "in" and _hit(m) and (best is None or float(m.get("ts") or 0) > best[0]):
                    best = (float(m.get("ts") or 0), {**m, "platform": plat, "chatId": chat, "messageId": m.get("id")})
        if best:
            return best[1]
        # …and a DESCRIPTION rather than a name: the message carrying most of its words wins; a tie or no word at
        # all finds nothing, it never picks one at random.
        import re as _re
        words = [w for w in _re.findall(r"[^\W\d_]{4,}", who)]
        if len(words) < 2:
            return None
        scored = []

        def _score(m) -> int:
            hay = (" ".join(str(m.get(k) or "") for k in ("from", "who", "senderId", "subject", "chatId"))
                   + " " + str(m.get("body") or "")[:200]).lower()   # a thread keeps the subject in its body
            return sum(1 for w in words if w in hay)
        for it in _d._visible_items(db):
            scored.append((_score(it), it))
        # …and the conversations this card keeps: a mail brought back from the history lands in a THREAD.
        seen = {str(it.get("messageId")) for _s, it in scored}
        for tkey, th in (db.get("threads") or {}).items():
            plat, _, chat = str(tkey).partition("|")
            for m in (th or {}).get("msgs") or []:
                if m.get("dir") == "in" and str(m.get("id")) not in seen:
                    scored.append((_score({**m, "chatId": chat}),
                                   {**m, "platform": plat, "chatId": chat, "messageId": m.get("id")}))
        scored.sort(key=lambda t: -t[0])
        if scored and scored[0][0] >= 2 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1]
        # …and the conversation that is OPEN, when it is the sender he described (one shared word is enough).
        # Another sender's open chat is never a stand-in.
        chat = db.get("active_chat") or {}
        th = (db.get("threads") or {}).get(f"{chat.get('platform')}|{chat.get('chatId')}") or {}
        hay = " ".join([str(chat.get(k) or "") for k in ("name", "chatId")]
                       + [str(m.get("who") or "") for m in (th.get("msgs") or []) if m.get("dir") == "in"]).lower()
        if not hay.strip() or not any(w in hay for w in words):
            return None
        n, mid = None, ""
    if n is not None or mid:
        for it in _d._visible_items(db):
            if (n is not None and str(it.get("n")) == str(n)) or (mid and str(it.get("messageId")) == mid):
                return it
        if not mid:
            return None
    chat = db.get("active_chat")
    if not chat:
        return None
    msgs = [m for m in _th.window(db, chat.get("platform"), chat.get("chatId")) if m.get("dir") == "in"]
    if mid:
        msgs = [m for m in msgs if str(m.get("id")) == mid]
    if not msgs:
        return None
    m = msgs[-1]
    return {**m, "platform": chat.get("platform"), "chatId": chat.get("chatId"), "messageId": m.get("id")}
