"""The mail family's reach: the INTERNALDATE of the oldest message in the INBOX (refactor2710-13 T-02).

Read-only (`select(..., readonly=True)`), one SEARCH and one FETCH of a single header-less item; the body is never
asked for. UIDs grow with arrival, so the lowest UID is the first item the mailbox can show.
"""
from __future__ import annotations

import imaplib
import time
from datetime import datetime, timezone

from connectors.reach import Reach

SOURCE = "imap:INBOX:INTERNALDATE"


def _iso(struct) -> str:
    return datetime.fromtimestamp(time.mktime(struct), tz=timezone.utc).isoformat(timespec="seconds")


def earliest_readable(mb=None) -> Reach:
    """`mb` is a `Mailbox` (anything with `_imap()`); None reads the configured one. Never raises."""
    if mb is None:
        from connectors.email import config
        mb = config.mailbox()
    if mb is None:
        return Reach(family="mail", provider="email", source=SOURCE, detail="not_connected")
    try:
        im = mb._imap()
    except Exception as e:  # noqa: BLE001 — a login that fails is the answer «unreachable», said as such
        return Reach(family="mail", provider="email", source=SOURCE, detail=f"login:{type(e).__name__}")
    try:
        im.select("INBOX", readonly=True)
        st, data = im.uid("search", None, "ALL")
        uids = (data[0].split() if st == "OK" and data and data[0] else [])
        if not uids:
            return Reach(family="mail", provider="email", source=SOURCE, detail="empty")
        first = uids[0].decode() if isinstance(uids[0], bytes) else str(uids[0])
        st, data = im.uid("fetch", first, "(INTERNALDATE)")
        raw = data[0] if st == "OK" and data else b""
        raw = raw[0] if isinstance(raw, tuple) else raw
        when = imaplib.Internaldate2tuple(raw if isinstance(raw, bytes) else str(raw).encode())
        if when is None:
            return Reach(family="mail", provider="email", source=SOURCE, detail="no_internaldate")
        return Reach(family="mail", provider="email", earliest=_iso(when), source=SOURCE)
    except Exception as e:  # noqa: BLE001
        return Reach(family="mail", provider="email", source=SOURCE, detail=type(e).__name__)
    finally:
        try:
            im.logout()
        except Exception as e:  # noqa: BLE001 — the answer is already in hand
            import logging
            logging.getLogger("zaelar.email.reach").debug(f"logout after reach failed: {e!r}")
