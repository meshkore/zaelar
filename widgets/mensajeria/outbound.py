"""widgets/mensajeria/outbound.py — writing to a PERSON who has not written to us (V2-683).

Every outbound path in this widget until now answered an existing conversation: `reply`, `draft` and
`send_draft` all resolve against a stored item or the open thread, and the queue they feed carries a
`chatId` that only exists because somebody already wrote. So «contacta con Iván Musikin» had no door at
all — not a missing tool, a missing DIRECTION.

This is that direction, and it is deliberately small: resolve WHO and by WHICH channel (both answered by
`widgets/directory.py`, never here), refuse honestly when either is in doubt, and hand the order to the
SAME queue → bus → connector seam a reply already travels. Nothing new reaches the network: each
connector keeps its own tested send.

## The refusals are the feature

A reply can only go to the conversation it answers, so the worst it can do is say the wrong thing to the
right person. This door can say the right thing to the WRONG person, which is not recoverable — so an
ambiguous name, a channel we cannot honour and an empty text all stop here, naming what is missing so the
next attempt can succeed. `resolve_target` never guesses and never picks the first row.

## Why an address may be given directly

«Manda un correo a reservas@…» is a real errand with no contact behind it, and an address IS a complete
capability (the module note in `directory.py`). It is accepted only when it looks like one and only for
email; the operator hears it in the confirmation before anything is sent, like every other send.
"""
from __future__ import annotations

import re
import time

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
    from . import data as _d
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


def enqueue_reply(db: dict, target: dict, text: str, cc: list | None = None) -> None:
    """The one place a reply/draft actually gets queued for the connector to send for real. A real item
    ALWAYS carries `messageId` (set on ingestion, by every connector) — including one resolved via `reply`'s
    own chat-grouping fallback, which never goes through `_renumber` and so never has `n` set either, which
    is why `n` cannot be the "is this real" signal here. Only the true synthetic thread-identity target (see
    `resolve_reply_target`, `{"platform", "chatId"}` alone) has neither, and nothing pending to remove —
    correct, since there was no pending item to begin with."""
    from . import data as _d
    db.setdefault("pending_reply", []).append({
        "platform": target.get("platform"), "chatId": target.get("chatId"),
        "to": target.get("senderId") or target.get("chatId"),
        "messageId": target.get("messageId"), "subject": target.get("subject", ""),
        "msgid": target.get("msgid", ""), "text": text,
        # V2-680 — reply-ALL. Empty (the default, and every caller that does not pass it) is a plain reply,
        # so the queued shape is unchanged for `reply` and for every connector that ignores the field.
        "cc": [str(a) for a in (cc or []) if str(a).strip()],
    })
    if target.get("messageId") is not None:
        db.setdefault("pending_read", []).append(_d._key(target))
        db["items"] = [it for it in db.get("items", []) if it is not target]


def _resolve_recipient(who: str):
    """Resolve a recipient reference to its directory contacts, tolerating the DECORATION the model appends.

    Measured 2026-09-15 (the manual meeting test): `send_to` was called with «Kryptonite (Telegram
    @cryptonitefund)» — name plus its channel note — and the send failed «no tengo a … en el directorio»
    over a contact that was right there. The name is the durable part; the parenthetical and trailing
    clauses are decoration. Peeled through the ONE shared matcher (`widgets/textmatch.spans`, V2-705), so
    «write to X (…)» resolves the same way «the meeting with X (…)» does. The FIRST span that resolves wins,
    and its result is returned verbatim — a span matching SEVERAL contacts is still the answer (the caller
    asks which), never silently the first."""
    from .. import textmatch
    d = _directory()
    for span in textmatch.spans(who):
        hits = d.resolve(span)
        if hits:
            return hits
    return []


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
    if not text:
        return {"ok": False, "error": "no me ha llegado el mensaje — vuelve a llamar a send_to con `text` "
                                      "(lo que hay que decirle), sin volver a preguntárselo al operador si "
                                      "ya te lo dijo"}
    if not who:
        return {"ok": False, "error": "no me ha llegado a quién — vuelve a llamar a send_to con `contact` "
                                      "(el nombre tal y como lo dijo el operador)"}

    hits = _resolve_recipient(who)
    d = _directory()
    if len(hits) > 1:
        names = " · ".join(f"{c.get('name')}" + (f" ({c.get('city')})" if c.get("city") else "")
                           for c in hits[:5])
        # The ambiguity is the answer: asking which one costs a turn, writing to the wrong person costs
        # something that cannot be taken back (the `refs.py` doctrine, at the one door where it is final).
        return {"ok": False, "error": f"tengo {len(hits)} contactos que encajan con «{who}»: {names}. "
                                      f"PREGÚNTALE al operador a cuál se refiere y vuelve a llamar a send_to "
                                      f"con el nombre completo."}
    if not hits:
        # No contact — an ADDRESS said out loud is still a complete way to reach somebody.
        if _EMAIL_RE.match(who) and want in ("", "email"):
            return {"ok": True, "platform": "email", "to": who, "chatId": who, "name": who,
                    "contactId": "", "known": False}
        return {"ok": False, "error": f"no tengo a «{who}» en el directorio. Si el operador te ha dado su "
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
            return {"ok": False, "error": f"no tengo el {label(want)} de {name} — {tail}. Pregúntale al "
                                          f"operador el dato que falta y guárdalo con contactos/set_channel."}
        if have:
            return {"ok": False, "error": f"{name} tiene varios canales ({', '.join(label(p) for p in have)}) "
                                          f"y ninguno marcado como preferido. PREGÚNTALE al operador por cuál "
                                          f"le escribe y vuelve a llamar a send_to con `channel`."}
        return {"ok": False, "error": f"no tengo ninguna forma de escribir a {name}: ni teléfono, ni usuario "
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


def new_ref() -> str:
    """The id that ties an order to its echo (`connector.msg_out`) and, through it, to an errand. Not a
    counter: a restart would repeat one, and the binding it carries must never land on somebody else's
    conversation (the `SessionRecord.sheet` scar, V2-259)."""
    import secrets
    return f"s{int(time.time() * 1000) % 10_000_000}-{secrets.token_urlsafe(6)}"


def enqueue(db: dict, target: dict, text: str, *, subject: str = "", objective: str = "",
            ref: str = "") -> dict:
    """Put ONE send in the store's outbound queue. The owner flushes it to the bus, exactly as it does with a
    reply — this function never touches the network and never publishes."""
    order = {
        "ref": ref or new_ref(),
        "platform": target.get("platform"),
        "to": target.get("to") or "",
        "chatId": target.get("chatId") or "",
        "name": target.get("name") or "",
        "contactId": target.get("contactId") or "",
        "text": str(text or ""),
        "at": time.time(),
    }
    if subject:
        order["subject"] = subject
    if objective:
        order["objective"] = objective
    db.setdefault("pending_send", []).append(order)
    return order
