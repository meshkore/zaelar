#
# found_mail.py — what an archive search FOUND, made usable by the card: a mail the card no longer holds is asked
# back from the mailbox, and the last find is remembered so «open it» has a referent. Moved out of data.py (which
# re-exports every name) with no behaviour change.
#
import time

from .. import store
from .shape import WIDGET_ID, load_db


_BRING_BACK_MAX = 2


def _bring_back_found_mail(payload: dict) -> int:
    """A mail the archive found but this card no longer holds is asked back from the mailbox, attachments included.

    Demo pass 2026-09-28 (full28 E1→E3): «did inworld send me something?» found the receipt in the archive; the card
    holds only the 30 most recent unread, and with newer mail since, the receipt was not among them — «open it» found
    no chat and «send the invoice to quinn» had nothing to forward. The archive keeps the mailbox UID, so the
    card's own «load previous» order (the connector's `fetch_older`, one message just below UID+1) brings exactly
    that mail into its conversation. Never raises; returns how many orders were queued."""
    try:
        from . import views as _v
        db = load_db()
        held = {str(it.get("chatId")) for it in db.get("items", []) if it.get("platform") == "email"}
        held |= {str(k).partition("|")[2] for k in (db.get("threads") or {}) if str(k).startswith("email|")}
        queued, seen = 0, set()
        for r in _v.archive_rows(payload):
            if queued >= _BRING_BACK_MAX:
                break
            chat, uid = str(r.get("chat_id") or ""), str(r.get("msg_id") or "")
            if (r.get("platform") != "email" or r.get("direction") != "in" or not chat or not uid.isdigit()
                    or chat in held or chat in seen):
                continue
            seen.add(chat)
            db.setdefault("pending_history", []).append(
                {"platform": "email", "chatId": chat, "beforeTs": 0, "beforeId": str(int(uid) + 1), "limit": 1})
            queued += 1
        if queued:
            store.save(WIDGET_ID, db)
        return queued
    except Exception:  # noqa: BLE001
        return 0


FOUND_TTL_S = 1800


def _remember_found(payload: dict) -> None:
    """The mail an archive search found, so «open it» has a referent (demo pass 62, E2).

    «did inworld send me something?» found the receipt; its conversation was on the card (a thread with no name,
    brought back by an earlier «load previous»), but not in the inbox list — and «open it» came back as «nothing to
    open», then a repair pass opened the ONE chat the list showed: the wrong mail. What the card last found is a
    fact of the card, like what it last sent. Never raises."""
    try:
        from . import views as _v
        row = next((r for r in _v.archive_rows(payload) if r.get("direction") == "in" and r.get("chat_id")), None)
        if row is None:
            return
        db = load_db()
        body = str(row.get("body") or "")
        subject = body[len("[Asunto: "):body.index("]")] if body.startswith("[Asunto: ") and "]" in body else ""
        db["last_found"] = {"platform": str(row.get("platform") or ""), "chatId": str(row.get("chat_id")),
                            "name": str(row.get("chat_name") or row.get("sender") or row.get("chat_id")),
                            "subject": subject[:120], "at": time.time()}
        store.save(WIDGET_ID, db)
    except Exception:  # noqa: BLE001
        pass


def last_found(db: dict) -> dict | None:
    """The fresh `last_found` of this card, or None."""
    lf = db.get("last_found")
    if isinstance(lf, dict) and lf.get("chatId") and time.time() - float(lf.get("at") or 0) < FOUND_TTL_S:
        return lf
    return None
