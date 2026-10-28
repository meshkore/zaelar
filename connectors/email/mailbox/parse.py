"""Raw RFC822 → the normalized dict the triage/store work on, with its attachments. Pure: no IMAP or SMTP here."""
import email as email_lib
import re

from connectors.email.headers import (decode_header_value, display_name, extract_email_address, extract_text_body,
                                      is_automated_sender, verify_sender_authentication)

MAX_BODY_LENGTH = 20_000          # triage only needs the body; trim huge emails


# ── Attachments (V2-543) ────────────────────────────────────────────────────
# BODY.PEEK[] already fetches the WHOLE MIME message; until now `extract_text_body` explicitly skipped every
# attachment and the bytes were discarded. This second walk saves them to `media_dir` (the messaging widget's
# own data dir, the one place its asset route serves) so the widget can preview a photo or link a PDF.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 5
_ATT_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def extract_attachments(msg, uid: str, media_dir: str) -> tuple[str | None, list[str]]:
    """Save attachment + inline-image parts to `media_dir`. Returns (mediaType, paths) — mediaType uses the
    shared connector vocabulary: 'image' when every saved part is an image, else 'document'. Pure enough to
    test with a built Message; only touches the filesystem it is handed. Best-effort per part."""
    import os
    from connectors.email import mailbox as _facade     # the size knob is the PACKAGE's: a test turns it there
    if not media_dir or not msg.is_multipart():
        return None, []
    limit = _facade.MAX_ATTACHMENT_BYTES
    paths: list[str] = []
    all_images = True
    n = 0
    for part in msg.walk():
        if n >= MAX_ATTACHMENTS:
            break
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()
        is_attachment = "attachment" in disp
        is_inline_image = ctype.startswith("image/") and (filename or part.get("Content-ID"))
        if not (is_attachment or is_inline_image):
            continue
        try:
            payload = part.get_payload(decode=True)
            if not payload or len(payload) > limit:
                continue
            base = decode_header_value(filename or "") or f"adjunto.{(ctype.split('/') + ['bin'])[1]}"
            safe = _ATT_SAFE.sub("_", base)[-80:] or "adjunto"
            name = f"eml_{uid}_{n}_{safe}"
            path = os.path.join(media_dir, name)
            with open(path, "wb") as fh:
                fh.write(payload)
            paths.append(path)
            if not ctype.startswith("image/"):
                all_images = False
            n += 1
        except Exception:
            continue
    if not paths:
        return None, []
    return ("image" if all_images else "document"), paths


def _other_recipients(msg, from_addr: str) -> list:
    """Addresses in To/Cc that are neither the sender nor us — what a reply-all adds over a reply.

    Our OWN address is dropped here rather than at send time: a reply-all that copies the operator on his
    own outgoing mail is a bug every real client avoids, and the address is only knowable at this layer.
    Order is preserved and duplicates collapsed (case-insensitively — an address is case-insensitive in its
    domain and every real mailbox treats the local part that way too)."""
    from email.utils import getaddresses
    mine = {(from_addr or "").strip().lower()}
    try:
        from connectors.email import config as _cfg
        own = _cfg.address().strip().lower()
        if own:
            mine.add(own)
    except Exception:
        pass                                   # no account configured: only the sender is excluded
    out, seen = [], set()
    for _name, addr in getaddresses([msg.get("To", ""), msg.get("Cc", "")]):
        a = (addr or "").strip()
        low = a.lower()
        if not a or "@" not in a or low in mine or low in seen:
            continue
        seen.add(low)
        out.append(a)
    return out[:25]                            # a mailing-list blast is not a conversation to answer


def _is_own_address(addr: str) -> bool:
    """A mail FROM the operator's own address is the echo of one he sent — a copy that lands back in INBOX when
    the recipient is a list or alias he is on. Demo pass 2026-09-28 (full13 E3): the invoice forwarded to Quinn
    in an earlier run came back as «operator@example.com · Hi Quinn, forwarding the Inworld invoice», sat first in
    his «for you» list, and the model took it for a mail FROM Quinn and asked which thread to send from. What
    he wrote himself is not something to triage for him."""
    try:
        from connectors.email import config as _cfg
        own = _cfg.address().strip().lower()
    except Exception:
        return False
    return bool(own) and (addr or "").strip().lower() == own


def parse_message(uid: str, raw_bytes: bytes, media_dir: str | None = None) -> dict | None:
    """Raw email (RFC822) → normalized dict for triage/store, or None if it should be ignored (automatic).
    `uid` = IMAP UID (str) → used as messageId (stable per mailbox). RFC Message-ID goes in `msgid`.
    `media_dir` (V2-543): where to save attachments; None (tests/legacy callers) skips them — parsing stays
    pure unless a destination is handed in."""
    msg = email_lib.message_from_bytes(raw_bytes)
    from_raw = msg.get("From", "")
    from_addr = extract_email_address(from_raw)
    headers = dict(msg.items())
    if is_automated_sender(from_addr, headers) or _is_own_address(from_addr):
        return None
    subject = decode_header_value(msg.get("Subject", "(sin asunto)"))
    body = (extract_text_body(msg) or "").strip()[:MAX_BODY_LENGTH]
    authok, why = verify_sender_authentication(msg, from_addr)
    out = {
        "senderName": display_name(from_raw, from_addr),
        "isGroup": False,                     # personal email is 1:1 (the thread is the "chat")
        "chatName": None,
        "body": (f"[Asunto: {subject}]\n{body}" if subject and not subject.startswith("Re:") else body) or "(vacío)",
        "messageId": str(uid),                # IMAP UID → dedup + mark-seen
        "chatId": from_addr,                  # the sender IS the thread/chat
        "senderId": from_addr,
        "subject": subject,
        "msgid": msg.get("Message-ID", ""),   # RFC Message-ID → reply threading
        "authenticated": authok,
        "auth_reason": why,
        # Everyone else the message went to (V2-680) — the only thing that makes a REPLY-ALL real. Without
        # it, offering the choice would send the identical single reply under a second name, which is worse
        # than not offering it: the operator would believe the other recipients were answered.
        "recipients": _other_recipients(msg, from_addr),
    }
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            out["timestamp"] = dt.timestamp()
    except Exception:
        pass
    if media_dir:
        try:
            mtype, paths = extract_attachments(msg, uid, media_dir)
        except Exception:
            mtype, paths = None, []
        if mtype:
            out["hasMedia"] = True
            out["mediaType"] = mtype
            out["mediaUrls"] = paths
    return out
