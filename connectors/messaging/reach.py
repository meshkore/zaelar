"""The messaging family's reach: the oldest message the ARCHIVE holds for a platform (refactor2710-13 T-02).

The archive is what a question about the past can search (V2-628), so its first row IS how far back this engine
can see on WhatsApp, Telegram or email — not how far the platform itself goes. Read through the archive's public
doors only (`chats` + `oldest`), so the answer follows the same patchable connection every test uses.
"""
from __future__ import annotations

from datetime import datetime, timezone

from connectors.reach import Reach

SOURCE = "archive:messages:min(ts)"


def earliest_readable(platform: str) -> Reach:
    from connectors.messaging import archive
    plat = (platform or "").strip().lower()
    if not plat:
        return Reach(family="messaging", provider=plat, source=SOURCE, detail="no_platform")
    firsts = [o["ts"] for c in archive.chats(plat) if (o := archive.oldest(plat, c["chatId"])) and o.get("ts")]
    if not firsts:
        return Reach(family="messaging", provider=plat, source=SOURCE, detail="empty")
    when = datetime.fromtimestamp(float(min(firsts)), tz=timezone.utc).isoformat(timespec="seconds")
    return Reach(family="messaging", provider=plat, earliest=when, source=SOURCE)
