"""\\Seen on and off, and the FLAGS line reader (V2-546). Mixed into `Mailbox`. What the operator did in his OWN
client: the server keeps per-message FLAGS (\\Seen = opened, \\Answered = replied, wherever he did it), so everything
the widget needed was one FETCH away — `membership.check` is that FETCH, and `_FLAG_RE` is how it reads each row."""
import re


class _FlagsMixin:
    _FLAG_RE = re.compile(rb"UID\s+(\d+).*?FLAGS\s+\(([^)]*)\)", re.IGNORECASE | re.DOTALL)

    def _store_flags(self, uids: list[str], op: str) -> bool:
        """`+FLAGS` / `-FLAGS` (\\Seen) on each UID, batch best-effort. True if the connection held."""
        uids = [u for u in (uids or []) if u]
        if not uids:
            return True
        try:
            im = self._imap()
            try:
                im.select("INBOX")
                for uid in uids:
                    try:
                        im.uid("store", uid, op, "(\\Seen)")
                    except Exception:
                        pass
            finally:
                im.logout()
            return True
        except Exception:
            return False

    def mark_seen(self, uids: list[str]) -> bool:
        """Mark the given UIDs as \\Seen (read on the server). True if OK (batch best-effort)."""
        return self._store_flags(uids, "+FLAGS")

    def mark_unseen(self, uids: list[str]) -> bool:
        """Take \\Seen OFF the given UIDs — the mail reads as unread again in his own client. True if OK.

        The operator's demo rule (2026-09-28): a mail the assistant opened for a rehearsal is left UNREAD at the
        end, never archived, so the same rehearsal can run again."""
        return self._store_flags(uids, "-FLAGS")
