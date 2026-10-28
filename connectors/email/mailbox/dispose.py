"""Archive / delete in the REAL mailbox (V2-543): folder discovery and the move out of INBOX. Mixed into `Mailbox`.

Before this, the connector's ONLY IMAP verbs were search/fetch/store+\\Seen — archiving or deleting a mail from the
widget had nowhere to go, so the operator had to open his real mailbox anyway. Folder discovery is RFC 6154
SPECIAL-USE first (Gmail/iCloud/Outlook all advertise it), common names second; Gmail's archive is its own case: it
advertises \\All (All Mail) and no \\Archive — there, expunging from INBOX IS archiving (label removal), the
documented default behavior of its IMAP bridge."""
import re


class _DisposeMixin:
    _FALLBACK_ARCHIVE = ("Archive", "Archivo")
    _FALLBACK_TRASH = ("Trash", "[Gmail]/Trash", "Deleted Messages", "Deleted Items", "Papelera")

    @staticmethod
    def _folders(im, *, delimiter: bool = False) -> list[tuple]:
        """LIST → [(attrs lowercase, folder name)], or [(attrs, name, hierarchy delimiter)] with `delimiter=True` —
        the delimiter is the server's own («/» on Gmail, «.» on many others; NIL when flat), and a reader that guesses
        it cuts «ana@example.com» down to «com». Best-effort parse; unparseable lines are skipped."""
        out: list[tuple] = []
        try:
            status, data = im.list()
            if status != "OK" or not data:
                return out
            for raw in data:
                line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
                m = re.match(r'\(([^)]*)\)\s+("[^"]*"|NIL|nil)\s+"?(.+?)"?\s*$', line)
                if m:
                    sep = "" if m.group(2).upper() == "NIL" else m.group(2).strip('"').replace("\\\\", "\\")
                    out.append((m.group(1).lower(), m.group(3), sep) if delimiter else (m.group(1).lower(), m.group(3)))
        except Exception:
            pass
        return out

    def _dispose_uids(self, im, uids: list[str], folder: str | None) -> bool:
        """Move `uids` out of INBOX: to `folder` when given (UID MOVE where advertised, else COPY+\\Deleted),
        plain \\Deleted otherwise; one EXPUNGE at the end. INBOX must already be selected."""
        moved_any = False
        caps = tuple((c if isinstance(c, str) else c.decode("ascii", "ignore")).upper()
                     for c in (getattr(im, "capabilities", None) or ()))
        can_move = "MOVE" in caps
        quoted = f'"{folder}"' if folder else None
        for uid in uids:
            try:
                if folder and can_move:
                    st, _ = im.uid("MOVE", uid, quoted)
                    moved_any = moved_any or st == "OK"
                    continue
                if folder:
                    st, _ = im.uid("COPY", uid, quoted)
                    if st != "OK":
                        continue
                im.uid("store", uid, "+FLAGS", "(\\Deleted)")
                moved_any = True
            except Exception:
                continue
        try:
            im.expunge()
        except Exception:
            pass
        return moved_any

    def _dispose(self, uids: list[str], kind: str) -> tuple[bool, str]:
        uids = [u for u in (uids or []) if u]
        if not uids:
            return True, "nada que hacer"
        try:
            im = self._imap()
        except Exception as e:
            return False, f"IMAP: {e}"
        try:
            folders = self._folders(im)
            by_attr = {name for attrs, name in folders}
            def attr_folder(flag: str) -> str | None:
                return next((name for attrs, name in folders if flag in attrs), None)
            im.select("INBOX")
            if kind == "archive":
                dest = attr_folder("\\archive")
                if dest is None and attr_folder("\\all") is not None:
                    # Gmail: no \Archive folder exists; expunging from INBOX removes the label and the mail
                    # stays in All Mail — that IS its archive.
                    ok = self._dispose_uids(im, uids, None)
                    return ok, ("archivado (fuera de Recibidos)" if ok else "no pude archivar")
                if dest is None:
                    dest = next((n for n in self._FALLBACK_ARCHIVE if n in by_attr), None)
                if dest is None:
                    return False, "el buzón no tiene carpeta de archivo"
                ok = self._dispose_uids(im, uids, dest)
                return ok, (f"archivado en {dest}" if ok else "no pude archivar")
            # trash
            dest = attr_folder("\\trash") or next((n for n in self._FALLBACK_TRASH if n in by_attr), None)
            ok = self._dispose_uids(im, uids, dest)   # dest None → plain \Deleted+EXPUNGE (true delete)
            return ok, ((f"movido a {dest}" if dest else "borrado del buzón") if ok else "no pude borrar")
        except Exception as e:
            return False, str(e)
        finally:
            try:
                im.logout()
            except Exception:
                pass

    def archive(self, uids: list[str]) -> tuple[bool, str]:
        """Archive the given INBOX UIDs in the REAL mailbox. Returns (ok, human reason)."""
        return self._dispose(uids, "archive")

    def trash(self, uids: list[str]) -> tuple[bool, str]:
        """Delete the given INBOX UIDs in the REAL mailbox (to Trash where one exists). Returns (ok, reason)."""
        return self._dispose(uids, "trash")
