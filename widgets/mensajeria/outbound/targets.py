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


# ── ANSWERING a conversation (moved here from data.py, byte for byte, V2-683) ──────────────────────────
# The extraction that paid for the new door: `data.py` sat at 899 of the ratchet's 900-line cap, and the
# seam was already drawn — everything below is about SENDING, which is what this module is. One direction
# only, the `views.py` contract: data.py imports this at the top, and the two helpers these need
# (`_renumber`, `_key`) are read back LAZILY, because they belong to the store shape and not to sending.

def resolve_reply_target(db: dict, n=None, mid: str | None = None) -> dict | None:
    """The identity `draft`/`send_draft` reply to (V2-611) — NOT `reply`, which keeps its own original,
    separately-tested resolution (chat-list numbering when no thread is open) unchanged.

    `n`/`messageId` resolve against the flat renumbered list — the same space read/dismiss/archive/trash/hide
    already use, and the same meaning `n` has there (an ITEM, never a `_group_chats` row). The compose bar
    always has the concrete item in hand for a single email (both `n` and `messageId`), so this never needs
    to guess between the two numbering spaces the way `reply`'s legacy fallback does. With NEITHER given and
    a thread open, it resolves to the conversation itself: the operator answering «the person I'm talking
    to», not a specific past message."""
    from .. import data as _d
    if n is not None or mid:
        # `n` only exists on an item once `_renumber` assigns it — a raw stored item never carries one, so
        # this must renumber first, exactly like every other n-addressed action in data.py (read/dismiss/
        # archive/trash/hide). Skipping it would make a bare `n` never resolve to anything at all outside a
        # test fixture that happened to pre-set the field (the mistake this comment exists to prevent again).
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
    # Every pending item in this thread is already read/answered — nothing left in `items` to mark-read or
    # remove, but the conversation still has an identity to reply to (V2-546: answering must not require an
    # unread message to exist first). `enqueue_reply` reads only platform/chatId/senderId from this shape.
    return {"platform": key[0], "chatId": key[1]}


def _resolve_recipient(who: str):
    """Resolve a recipient reference to its directory contacts, tolerating the DECORATION the model appends.

    Measured 2026-09-15 (the manual meeting test): `send_to` was called with «Kryptonite (Telegram
    @northfunddemo)» — name plus its channel note — and the send failed «no tengo a … en el directorio»
    over a contact that was right there. The name is the durable part; the parenthetical and trailing
    clauses are decoration. Peeled through the ONE shared matcher (`widgets/textmatch.spans`, V2-705), so
    «write to X (…)» resolves the same way «the meeting with X (…)» does. The FIRST span that resolves wins,
    and its result is returned verbatim — a span matching SEVERAL contacts is still the answer (the caller
    asks which), never silently the first."""
    from ... import textmatch
    d = _directory()
    for span in textmatch.spans(who):
        hits = d.resolve(span, tolerant=False)
        if hits:
            return hits
    return []


def _near_recipient(who: str) -> list[dict]:
    """The contacts only a spelling-tolerant match finds — never written to, named back as a question (the operator,
    2026-10-15: «no podemos dejar con una duda quién es el destinatario»). «Kryptonite» → «¿te refieres a
    Cryptonite?» costs one turn; the wrong person costs what cannot be taken back."""
    from ... import textmatch
    d = _directory()
    for span in textmatch.spans(who):
        hits = d.near(span)
        if hits:
            return hits
    return []


def _one_mailbox(hits: list[dict], want: str, d) -> list[dict]:
    """Several contacts that all reach the SAME place are one recipient — [the first] — else [].

    Demo pass 54 (2026-09-29, E3): the same-turn correction retried the forward with the address itself, and the
    directory held two contacts carrying it («Andrés Garcia · Quinn»). Asking which costs the turn and cannot
    change where the mail goes. Two contacts with DIFFERENT channels stay an ambiguity, as before."""
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
        # conversation this card keeps. Demo pass 2026-09-28: the model forwarded `n: 2` — a guess, the Inworld
        # receipt was not on the visible list — and n 2 was somebody else's mail.
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
        # …and a DESCRIPTION rather than a name (demo pass 52, E3: «Inworld invoice email from September 27, 2026»
        # matched nothing as one string, and the retry guessed another sender): the message that carries most of its
        # words wins; a tie or no word at all finds nothing, it never picks one at random.
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
        # …and the conversations this card keeps: a mail brought back from the history lands in a THREAD, not on the
        # visible list (demo pass 53, E3: «Inworld AI receipt invoice2281-4878» — the receipt was in its thread).
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
        # …and the conversation that is OPEN, when it is the sender he described (demo passes 122-124, E3: E2 opened
        # the Inworld mail and the forward said «el recibo de Inworld» — one word in common with an English mail, so
        # the description found nothing and «this one» was refused). Another sender's open chat is never a stand-in.
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
