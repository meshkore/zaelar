"""The INBOX reads (read/unread, new, scrollback, activity): BODY.PEEK, never raising upward. Mixed into `Mailbox`."""
from .parse import parse_message


def _fetch_parsed(im, uid: str, media_dir: str | None) -> dict | None:
    """One UID, fetched with BODY.PEEK and parsed; None when the server has nothing or the parse fails."""
    st, msg_data = im.uid("fetch", uid, "(BODY.PEEK[])")
    if st != "OK" or not msg_data or not msg_data[0]:
        return None
    try:
        parsed = parse_message(uid, msg_data[0][1], media_dir=media_dir)
    except Exception:
        parsed = None
    return parsed


class _ReadsMixin:
    def inbox_split(self) -> tuple[set[str], list[str]]:
        """`(uids ALREADY READ, uids UNREAD oldest-first)` — what `seen` should be seeded with, and what should not.

        V2-606. `all_uids` seeded `seen` with the WHOLE inbox, so the widget could only ever show mail arriving
        AFTER the connector started. Measured on the operator's real mailbox: 1110 in INBOX, **1088 of them
        UNSEEN** — every one of which was marked «already seen» on connect, and again on every restart, because
        `_seen` lives in memory. The connector authenticated, reported «Conectado» and showed him nothing,
        forever, which is exactly what he reported as «the Gmail thing doesn't work».

        The line the seeding should draw is the one the operator already draws: mail he has READ is dealt with
        and does not come back; mail he has NOT read is the thing he is asking to see. Two searches instead of
        one, and IMAP does the work — no flag is written and no body is fetched here.

        Fail-soft: on any failure returns `(everything, [])`, which is the OLD behaviour — a connector that
        cannot tell read from unread must not suddenly dump a whole mailbox into the widget.
        """
        try:
            im = self._imap()
        except Exception:
            return self.all_uids(), []
        try:
            im.select("INBOX")

            def _search(query: str) -> list[str]:
                st, data = im.uid("search", None, query)
                if st != "OK" or not data or not data[0]:
                    return []
                return [u.decode() if isinstance(u, bytes) else str(u) for u in data[0].split()]

            read, unread = set(_search("SEEN")), _search("UNSEEN")
            if not read and not unread:          # nothing came back at all → do not treat it as an empty mailbox
                return self.all_uids(), []
            return read, unread
        except Exception:
            return self.all_uids(), []
        finally:
            try:
                im.logout()
            except Exception:
                pass

    def all_uids(self) -> set[str]:
        """All current INBOX UIDs. Kept as the fail-soft floor for `inbox_split`."""
        out: set[str] = set()
        try:
            im = self._imap()
            try:
                im.select("INBOX")
                status, data = im.uid("search", None, "ALL")
                if status == "OK" and data and data[0]:
                    out = {u.decode() if isinstance(u, bytes) else str(u) for u in data[0].split()}
            finally:
                im.logout()
        except Exception:
            pass
        return out

    def fetch_new(self, seen: set[str], media_dir: str | None = None) -> list[dict]:
        """Return INBOX emails whose UID is not in `seen`, parsed and normalized (without marking \\Seen — uses
        BODY.PEEK). Does NOT mutate `seen` (caller does it after publishing). Never raises upward.
        `media_dir` (V2-543): destination for attachments; None keeps the old text-only behavior."""
        results: list[dict] = []
        try:
            im = self._imap()
        except Exception:
            return results
        try:
            im.select("INBOX")
            status, data = im.uid("search", None, "ALL")
            if status != "OK" or not data or not data[0]:
                return results
            for raw_uid in data[0].split():
                uid = raw_uid.decode() if isinstance(raw_uid, bytes) else str(raw_uid)
                if uid in seen:
                    continue
                parsed = _fetch_parsed(im, uid, media_dir)
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

    def fetch_older(self, address: str, before_uid: str, limit: int = 30,
                    media_dir: str | None = None) -> tuple[list[dict], bool]:
        """Mail from `address` OLDER than `before_uid` ("load previous"). Returns (messages, reached_start).

        UIDs are monotonic per mailbox, so "older" is a numeric comparison and needs no date arithmetic. Uses
        BODY.PEEK like every other read here: fetching the scrollback of a conversation must not mark it read."""
        try:
            cutoff = int(str(before_uid))
        except (TypeError, ValueError):
            return [], False
        results: list[dict] = []
        reached_start = False
        try:
            im = self._imap()
        except Exception:
            return results, False
        try:
            im.select("INBOX")
            safe = (address or "").replace('"', "")
            st, data = im.uid("search", None, "FROM", f'"{safe}"')
            if st != "OK" or not data or not data[0]:
                return results, True          # nothing from them at all: there is no earlier mail to offer
            older = sorted((int(u) for u in data[0].split() if int(u) < cutoff))
            reached_start = len(older) <= limit
            for uid in older[-limit:]:
                parsed = _fetch_parsed(im, str(uid), media_dir)
                if parsed is not None:
                    results.append(parsed)
        except Exception:
            return results, False
        finally:
            try:
                im.logout()
            except Exception:
                pass
        return results, reached_start

    def search_since(self, hours: float, limit: int = 100,
                     media_dir: str | None = None) -> list[dict]:
        """INBOX mail from the last `hours` hours, newest capped at `limit`, parsed (V2-624 — the platform-wide
        pull: «tráete la actividad de las últimas 72 horas»). IMAP's SINCE compares the internal date at DAY
        granularity, so the search over-fetches to the start of the cutoff day and the SERVICE trims by the
        message's own timestamp — this method promises «no older than the cutoff day», not the exact hour.
        BODY.PEEK like every read here: pulling activity must not mark anything read."""
        import datetime as _dt
        results: list[dict] = []
        try:
            im = self._imap()
        except Exception:
            return results
        try:
            im.select("INBOX")
            since = (_dt.datetime.now() - _dt.timedelta(hours=float(hours))).strftime("%d-%b-%Y")
            st, data = im.uid("search", None, "SINCE", since)
            if st != "OK" or not data or not data[0]:
                return results
            uids = sorted(int(u) for u in data[0].split())
            for uid in uids[-max(1, int(limit)):]:
                parsed = _fetch_parsed(im, str(uid), media_dir)
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
