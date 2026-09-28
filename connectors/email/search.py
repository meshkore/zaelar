"""connectors/email/search.py — find mail in the REAL mailbox by sender or subject (demo pass 30, 2026-09-28).

Its own module because `mailbox.py` is over the architecture ratchet's ceiling: a new capability goes where it
can live, not into the file the ratchet is asking to shrink. It uses the mailbox's own connection and parser.
"""
from __future__ import annotations

from connectors.email.mailbox import parse_message


def search_text(mb, terms: list[str], limit: int = 5, media_dir: str | None = None) -> list[dict]:
    """INBOX mail whose SENDER or SUBJECT contains any of `terms`, newest first, parsed, at most `limit`.

    Demo pass 30 (2026-09-28, E1): «did inworld send me something?» — the receipt was the 34th newest unread,
    the card backfills 30, and after a reset the archive held nothing older, so the answer was «nothing from
    Inworld». The mailbox itself answers that question in one SEARCH. The folder is selected READ-ONLY and
    fetched with BODY.PEEK: looking for a mail must never mark it read (the demo's original stays unread)."""
    terms = [str(t).replace('"', "").strip() for t in (terms or []) if str(t).strip()][:4]
    results: list[dict] = []
    if not terms:
        return results
    try:
        im = mb._imap()
    except Exception:
        return results
    try:
        im.select("INBOX", readonly=True)
        uids: set[int] = set()
        for t in terms:
            st, data = im.uid("search", None, "OR", "FROM", f'"{t}"', "SUBJECT", f'"{t}"')
            if st == "OK" and data and data[0]:
                uids |= {int(u) for u in data[0].split()}
        for uid in sorted(uids, reverse=True)[:max(1, int(limit))]:
            st2, msg_data = im.uid("fetch", str(uid), "(BODY.PEEK[])")
            if st2 != "OK" or not msg_data or not msg_data[0]:
                continue
            try:
                parsed = parse_message(str(uid), msg_data[0][1], media_dir=media_dir)
            except Exception:
                parsed = None
            if parsed is not None:
                results.append(parsed)
    except Exception:
        pass
    finally:
        try:
            im.logout()
        except Exception:
            pass
    return results
