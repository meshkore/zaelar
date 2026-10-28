"""widgets/mensajeria/outbound/queue.py — putting a send in the store's outbound QUEUE: replies and new messages,
the files a forward carries (asked of the real mailbox when the card does not hold them), and the guard that keeps
the same files to the same person from leaving twice. Nothing here touches the network.
"""
from __future__ import annotations

import re
import time

from .targets import _message_ref


def enqueue_reply(db: dict, target: dict, text: str, cc: list | None = None,
                  attachments: list | None = None, not_before: float = 0.0, ref: str = "") -> None:
    """The one place a reply/draft is queued for the connector to send. `messageId` (set on ingestion), never
    `n`, is the "real item" signal: only the synthetic thread identity (`resolve_reply_target`, platform + chatId
    alone) lacks it, and it has no pending item to remove."""
    from .. import data as _d
    db.setdefault("pending_reply", []).append({
        "platform": target.get("platform"), "chatId": target.get("chatId"),
        "to": target.get("senderId") or target.get("chatId"),
        "messageId": target.get("messageId"), "subject": target.get("subject", ""),
        "msgid": target.get("msgid", ""), "text": text,
        # Reply-ALL (V2-680); empty is a plain reply, the shape every connector that ignores it expects.
        "cc": [str(a) for a in (cc or []) if str(a).strip()],
        # Local paths inside the widget's data dir (media.local_paths): photos, voice notes, documents.
        "attachments": [str(a) for a in (attachments or []) if str(a).strip()],
        # V2-800 — a reply he asked to send LATER waits in the queue until then (`take_pending_reply`).
        **({"not_before": float(not_before), "at": time.time(), "scheduled": True} if not_before else {}),
        # V2-819 — the card's send names itself, so the connector's echo or failure settles ITS outbox row.
        **({"ref": str(ref)} if ref else {}),
    })
    if target.get("messageId") is not None:
        db.setdefault("pending_read", []).append(_d._key(target))
        db["items"] = [it for it in db.get("items", []) if it is not target]


def new_ref() -> str:
    """The id that ties an order to its echo (`connector.msg_out`) and, through it, to an errand. Not a counter: a
    restart would repeat one, and the binding must never land on somebody else's conversation (V2-259)."""
    import secrets
    return f"s{int(time.time() * 1000) % 10_000_000}-{secrets.token_urlsafe(6)}"


#: (chatId, UID) → the local paths one read-only mailbox fetch brought this session. The pre-check and the send
#: both ask; the mailbox is read once.
_MAILBOX_FILES: dict[tuple[str, str], list[str]] = {}
_MAILBOX_MAX_ASKS = 2


def _mailbox_files(chat_id: str, uid: str) -> list[str]:
    """The files of ONE mail, asked of the real mailbox by its UID and saved where the card's assets live.

    A mail brought back as an archive row has no bytes; `fetch_older` with the UID just above it returns exactly
    that mail (UIDs are monotonic), BODY.PEEK, attachments saved by `parse_message`. [] when email is not
    connected, the UID is not one, or the fetch brings nothing."""
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
        from ... import store
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
            core = " ".join(re.sub(r"\([^)]*\)|#\S+", " ", who).split())   # «X (recibo #N)» → «X»
            if not rows and core and core != who:
                rows = archive.search(None, sender=core, platform="email", direction="in", limit=2)
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
    from ... import store
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
    """The refusal a `forward` would get from the owner for pointing at a message with no files, computed BEFORE
    the order is queued so it reaches the turn (the owner's refusal is out of sight). None when it has files."""
    src = {k: payload[k] for k in ("n", "messageId", "from") if payload.get(k) not in (None, "")}
    if attachments_of(db, src):
        return None
    # What is forwarded is what HE pointed at, never a stand-in from another sender that has files.
    return {"ok": False, "error": "el mensaje que él señaló no está en la tarjeta con sus adjuntos todavía — ábrelo "
                                  "(open con su remitente) y vuelve a intentarlo, o dile que aún no lo tienes a mano; "
                                  "NUNCA reenvíes el mensaje de otro remitente en su lugar"}


def enqueue(db: dict, target: dict, text: str, *, subject: str = "", objective: str = "",
            ref: str = "", attachments: list | None = None, not_before: float = 0.0,
            scheduled: bool = False) -> dict:
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
        db["recent_files_sent"] = [r for r in db.get("recent_files_sent") or [] if order["at"] - r["at"] <= SAME_FILES_S] \
            + [{"ref": order["ref"], "to": _send_key(order), "files": _file_key(attachments), "at": order["at"]}]
    if not_before:
        order["not_before"] = float(not_before)   # held in the queue until then — see `take_pending_send`
        if scheduled:
            order["scheduled"] = True             # V2-800: HE asked for later (not the few seconds of typing on screen)
    db.setdefault("pending_send", []).append(order)
    return order


#: How long the same files to the same person count as ONE send.
SAME_FILES_S = 180.0


def _send_key(t: dict) -> str:
    return f"{t.get('platform') or ''}|{str(t.get('to') or t.get('chatId') or '').strip().lower()}"


def _file_key(paths) -> list[str]:
    import os
    return sorted(os.path.basename(str(p)) for p in paths or [])


def same_files_just_sent(db: dict, target: dict, attachments) -> dict | None:
    """The send that carried these very files to this very person a moment ago, or None."""
    now, key, files = time.time(), _send_key(target), _file_key(attachments)
    return next((r for r in db.get("recent_files_sent") or []
                 if now - float(r.get("at") or 0) <= SAME_FILES_S and r.get("to") == key and r.get("files") == files), None)
