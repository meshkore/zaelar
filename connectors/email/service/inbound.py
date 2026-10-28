"""What comes IN: new mail off the INBOX, and what the operator did in his own client (V2-546, V2-807 T-04)."""
import asyncio

from loguru import logger

from connectors.email import config
from connectors.messaging import ingest, notify, store, triage


def _media_dir() -> str | None:
    """Where attachments land (V2-543): the messaging widget's own data dir — the one place its asset route
    serves. None on any failure → the mail still arrives, text-only, like before."""
    try:
        from widgets import store as wstore
        return wstore.data_dir("mensajeria")
    except Exception:
        return None


async def _ingest_new(mb) -> None:
    """Read INBOX in a thread, publish/triage new emails. Updates `_seen`/`_published`."""
    msgs = await asyncio.to_thread(mb.fetch_new, _svc._seen, _media_dir())
    if not msgs:
        return
    for m in msgs:
        _svc._seen.add(m.get("messageId"))
    if ingest.v2_enabled():
        for m in msgs:
            mid = m.get("messageId")
            if mid and mid not in _svc._published:
                _svc._published.add(mid)
                ingest.publish_msg(_svc.PLATFORM, m)
        return
    # Direct path (duo/hermes): triage + store + notification, like WhatsApp/Telegram.
    verdicts = await triage.classify(msgs, config.operator_name() or None)
    # V2-607 — the direct path splits the same two questions as the v2 owner: what is NEW goes into his
    # inbox, and only then is a notice considered. Before, `notify.surface` decided BOTH, so flipping the
    # notification default to silence would have left this path storing nothing at all — a connected
    # channel showing an empty list, which is the exact failure V2-606 had just fixed.
    fresh = store.new_among(store.load(), _svc.PLATFORM, verdicts)
    if not fresh:
        return
    for v in fresh:
        _svc._shown.add(v.get("messageId"))
        v["from"] = v.get("senderName") or v.get("chatId") or "?"
        v["group"] = None
    store.upsert_items(_svc.PLATFORM, fresh)
    notice = notify.deserving(fresh)
    logger.info(f"Email: +{len(fresh)} ({len(notice)} avisan)")
    if notice:
        await notify.announce("Email", notice)


#: A folder page he looked at within this long is kept in step with the server; one left alone is not asked about.
MIRROR_RECENT_S = 900


def on_screen(db: dict) -> dict[str, list[str]]:
    """{folder: [uid]} of what the card shows: the pending Inbox items, and the first rows of every folder list he
    LOOKED at recently (`viewed_at`, stamped when he enters it; the card's `mailbox.lists` are keyed `folder` or
    `folder#category`). Bounded by what is on screen, never by the size of the mailbox."""
    import time as _t
    out: dict[str, list[str]] = {}
    inbox = [str(it.get("messageId")) for it in db.get("items") or []
             if it.get("platform") == _svc.PLATFORM and it.get("messageId")]
    if inbox:
        out["INBOX"] = inbox
    for key, lst in ((db.get("mailbox") or {}).get("lists") or {}).items():
        try:
            recent = _t.time() - float((lst or {}).get("viewed_at") or 0) < MIRROR_RECENT_S
        except (TypeError, ValueError):
            recent = False
        if recent:
            out.setdefault(str(key).split("#", 1)[0], []).extend(
                str(r.get("uid")) for r in (lst.get("rows") or [])[:60] if isinstance(r, dict))
    return {f: list(dict.fromkeys(u)) for f, u in out.items() if u}


def pages_to_reread(db: dict, folder: str, exists) -> list[str]:
    """The recently viewed pages of `folder` whose size changed since they were read — mail arrived, or came back
    from where he had moved it. Their first page is read again; a page read before the size was recorded is not."""
    import time as _t
    out = []
    if exists is None:
        return out
    for key, lst in ((db.get("mailbox") or {}).get("lists") or {}).items():
        if str(key).split("#", 1)[0] != folder or (lst or {}).get("exists") in (None, exists):
            continue
        try:
            if _t.time() - float(lst.get("viewed_at") or 0) < MIRROR_RECENT_S:
                out.append(str(key))
        except (TypeError, ValueError):
            logger.debug(f"Email: unreadable view time on {key!r}, not re-read")
    return out


async def _reread_first_page(mb, key: str, lst: dict | None = None) -> None:
    from connectors.email import folders as _folders
    folder, _, category = key.partition("#")
    extra = {"category": category, "routes": (lst or {}).get("routes") or []} if category else {}
    page = await asyncio.to_thread(_folders.list_page, mb, folder, None, 30, **extra)
    ingest.publish_mailbox(_svc.PLATFORM, {"folder": folder, "before": None, **page})


async def _poll_external_flags(mb) -> None:
    """Mirror what the operator did in his own mail client (V2-546, V2-807 T-04).

    Two answers per folder on screen, from one login (`membership.check`): which of those messages the folder
    STILL holds, and their flags. A mail he archived, deleted or moved elsewhere has left the folder and leaves the
    card (`connector.mailbox` `{folder, gone}`); \\Seen means he opened it and \\Answered that he replied — either
    way it has been dealt with. Per message, never a watermark: IMAP is the one source that is exact about WHICH.

    Scoped to what the card shows, so its cost is the size of the screen and not of the mailbox; nothing on
    screen, nothing asked. A folder the server could not be asked about changes nothing."""
    if not ingest.v2_enabled():
        return
    try:
        db = store.load()
    except Exception:  # noqa: BLE001
        return
    shown = on_screen(db)
    if not shown:
        return
    from connectors.email import membership
    pending = [it for it in db.get("items", []) if it.get("platform") == _svc.PLATFORM]
    for folder, uids in shown.items():
        answer = await asyncio.to_thread(membership.check, mb, folder, uids)
        left = membership.gone(uids, answer)
        if left:
            ingest.publish_mailbox(_svc.PLATFORM, {"folder": folder, "gone": left})
            logger.info(f"Email: {len(left)} left {folder} in his own client (archived, deleted or moved)")
        lists = (db.get("mailbox") or {}).get("lists") or {}
        for key in pages_to_reread(db, folder, (answer or {}).get("exists")):
            await _reread_first_page(mb, key, lists.get(key))
        if answer is None or folder.upper() != "INBOX":
            continue
        by_chat: dict[str, list[str]] = {}
        for it in pending:
            got = answer["flags"].get(str(it.get("messageId")))
            if got and ("\\Seen" in got or "\\Answered" in got):
                by_chat.setdefault(str(it.get("chatId")), []).append(str(it.get("messageId")))
        for chat_id, ids in by_chat.items():
            ingest.publish_read(_svc.PLATFORM, chat_id, ids=ids)
            logger.info(f"Email: {len(ids)} read or answered in his own client ({chat_id})")


from connectors.email import service as _svc  # noqa: E402 — the facade: this module reads its state back
