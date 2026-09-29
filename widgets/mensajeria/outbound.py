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


def _one_mailbox(hits: list[dict], want: str, d) -> list[dict]:
    """Several contacts that all reach the SAME place are one recipient — [the first] — else [].

    Demo pass 54 (2026-09-29, E3): the same-turn correction retried the forward with the address itself, and the
    directory held two contacts carrying it («Andrés Garcia · Andrew»). Asking which costs the turn and cannot
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
        hits = _one_mailbox(hits, want, d) or hits
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


def _message_ref(db: dict, ref: dict) -> dict | None:
    """ONE message the operator points at: `n` of the list on screen, a `messageId`, or — with neither — the
    last message received in the conversation that is OPEN (what «this email» means). Its item or thread row."""
    from . import data as _d, thread as _th
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
        # …and a DESCRIPTION rather than a name (demo pass 52, E3: «Inworld receipt email from September 27, 2026»
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
        return None
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


#: (chatId, UID) → the local paths one read-only mailbox fetch brought this session. The pre-check and the send
#: both ask; the mailbox is read once.
_MAILBOX_FILES: dict[tuple[str, str], list[str]] = {}
_MAILBOX_MAX_ASKS = 2


def _mailbox_files(chat_id: str, uid: str) -> list[str]:
    """The files of ONE mail, asked of the real mailbox by its UID and saved where the card's assets live.

    Demo passes 38-53 (2026-09-29, E3): the receipt reached the card from the archive — a row, no bytes — and
    «send the invoice to andrew» was refused six times for files that were one IMAP read away. `fetch_older`
    with the UID just above it returns exactly that mail (UIDs are monotonic), BODY.PEEK, attachments saved by
    `parse_message`. [] when email is not connected, the UID is not one, or the fetch brings nothing."""
    import os
    key = (str(chat_id or "").strip(), str(uid or "").strip())
    if not key[0] or not key[1].isdigit():
        return []
    if key in _MAILBOX_FILES:
        return [p for p in _MAILBOX_FILES[key] if os.path.isfile(p)]
    paths: list[str] = []
    try:
        from connectors.email import config as _ecfg
        mb = _ecfg.mailbox()
        if mb is None:
            return []
        from .. import store
        msgs, _complete = mb.fetch_older(key[0], str(int(key[1]) + 1), 1, store.data_dir("mensajeria"))
        for m in msgs or []:
            if str((m or {}).get("messageId") or "") == key[1]:
                paths = [str(p) for p in (m.get("mediaUrls") or []) if os.path.isfile(str(p))]
    except Exception:  # noqa: BLE001 — a fetch that fails is the refusal the caller already knew how to give
        paths = []
    _MAILBOX_FILES[key] = paths
    return paths


def _mail_identities(m: dict | None, ref: dict) -> list[tuple[str, str]]:
    """Where the mail he points at lives in the mailbox — (chatId, UID) pairs, the message found on the card first,
    then what the ARCHIVE holds for the sender or description he gave. Never a mail of another sender: the archive
    is asked by sender, and the free-text search only over inbound mail that matches his words."""
    out: list[tuple[str, str]] = []
    if m and str(m.get("platform") or "email") == "email":
        out.append((str(m.get("chatId") or ""), str(m.get("messageId") or m.get("id") or "")))
    who = str((ref or {}).get("from") or "").strip()
    if who and len(out) < _MAILBOX_MAX_ASKS:
        try:
            from connectors.messaging import archive
            rows = archive.search(None, sender=who, platform="email", direction="in", limit=2)
            if not rows:
                rows = archive.search(who, platform="email", direction="in", limit=2)
            for r in rows:
                out.append((str(r.get("chat_id") or ""), str(r.get("msg_id") or "")))
        except Exception:  # noqa: BLE001
            pass
    seen: set[tuple[str, str]] = set()
    keep = []
    for pair in out:
        if pair[0] and pair[1].isdigit() and pair not in seen:
            seen.add(pair)
            keep.append(pair)
    return keep[:_MAILBOX_MAX_ASKS]


def attachments_of(db: dict, ref: dict) -> list[str]:
    """The files of the message he points at, as local paths inside this widget's own data dir — the only
    place they can be (the connector saved them there on ingestion, and the asset route serves nothing else).
    A mail the card holds WITHOUT them (brought back as an archive row) gets them from the mailbox, in the turn."""
    import os
    from .. import store
    m = _message_ref(db, ref)
    base = store.data_dir("mensajeria")
    out = []
    for med in (m or {}).get("media") or []:
        name = os.path.basename(str((med or {}).get("name") or ""))
        path = os.path.join(base, name)
        if name and os.path.isfile(path):
            out.append(path)
    if out:
        return out
    for chat_id, uid in _mail_identities(m, ref):
        got = _mailbox_files(chat_id, uid)
        if got:
            return got
    return []


def forward_without_files(db: dict, payload: dict) -> dict | None:
    """The refusal a `forward` would get from the owner for pointing at a message with no files — computed
    BEFORE the order is queued. Demo pass 37 (2026-09-29, E3): `forward {n: 1}` pointed at our own mail to
    Andrew; the owner refused it `no_attachment` out of sight and the turn went on as if the invoice had gone.
    Answered here, the refusal reaches the turn and its same-turn correction. None when the message has files."""
    src = {k: payload[k] for k in ("n", "messageId", "from") if payload.get(k) not in (None, "")}
    if attachments_of(db, src):
        return None
    # Demo pass 45 (E3): «…o el `n` del que los trae» sent the same-turn correction looking for ANY sender with
    # files — it retried with `from: Harry Boyd`. What is forwarded is what HE pointed at, never a stand-in.
    return {"ok": False, "error": "el mensaje que él señaló no está en la tarjeta con sus adjuntos todavía — ábrelo "
                                  "(open con su remitente) y vuelve a intentarlo, o dile que aún no lo tienes a mano; "
                                  "NUNCA reenvíes el mensaje de otro remitente en su lugar"}


def enqueue(db: dict, target: dict, text: str, *, subject: str = "", objective: str = "",
            ref: str = "", attachments: list | None = None, not_before: float = 0.0) -> dict:
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
    if attachments:
        order["attachments"] = [str(a) for a in attachments]
    if not_before:
        order["not_before"] = float(not_before)   # held in the queue until then — see `take_pending_send`
    db.setdefault("pending_send", []).append(order)
    return order
