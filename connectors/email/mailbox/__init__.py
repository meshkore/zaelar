#
# connectors/email/mailbox — PURE IMAP/SMTP logic for the email connector (V2-051). VENDORED + adapted from Hermes'
# email adapter (~/.hermes/hermes-agent/plugins/platforms/email/adapter.py), which is pure stdlib (imaplib/smtplib).
# There is NO asyncio or bus here: these are SYNCHRONOUS and blocking functions/classes (the service runs them in
# asyncio.to_thread), and 100% testable without network (parsers are pure). Does not depend on any internal Hermes
# class.
#
# Differences from Hermes (on purpose):
#   · We read the operator's OWN MAILBOX (we do not accept commands from senders) → SPF/DKIM/DMARC verification is
#     a trust METADATA field (`authenticated`), NOT an authorization gate.
#   · FETCH with BODY.PEEK[] → does NOT mark \Seen when reading; marking read is an EXPLICIT operator action
#     (mark_seen).
#   · Dedup by IMAP UID (stable per mailbox) = the store `messageId`; RFC Message-ID is stored separately (`msgid`)
#     for reply threading.
#
# One concern per module (refactor2710-13): `parse`, `smtp`, `reads`, `dispose`, `flags`; `Mailbox` mixes them in.
#
import imaplib

# ── Provider presets (IMAP/SMTP host) ───────────────────────────────────────────────────────────────────────────
# The SINGLE provider registry lives in `providers.py` (V2-055). Here we re-export the legacy hosts map `PRESETS`
# for compatibility with callers that imported it from this module (config.py).
from connectors.email.providers import PRESETS  # noqa: F401  (compatibility re-export)
from connectors.email.headers import (  # noqa: F401 — V2-778 F1: moved, imported back under their names
    decode_header_value, display_name, extract_email_address, extract_text_body, strip_html)
from .dispose import _DisposeMixin
from .flags import _FlagsMixin
from .parse import MAX_ATTACHMENT_BYTES, _other_recipients, extract_attachments, parse_message  # noqa: F401
from .reads import _ReadsMixin
from .smtp import _SmtpMixin, xoauth2_sasl

_IMAP_TIMEOUT = 30


# ── The mailbox: connection + operations (blocking; service runs them in to_thread) ─────────────────────────────
class Mailbox(_ReadsMixin, _FlagsMixin, _DisposeMixin, _SmtpMixin):
    """IMAP (read) + SMTP (send) connection. No persistent network state: each operation opens/closes its connection
    (robust to network drops; polling is every N seconds, not a live IDLE connection)."""

    def __init__(self, address: str, password: str, imap_host: str, imap_port: int,
                 smtp_host: str, smtp_port: int, auth_mode: str = "password", token: str = ""):
        self.address = (address or "").strip()
        self.password = password or ""
        self.imap_host = (imap_host or "").strip()
        self.imap_port = int(imap_port or 993)
        self.smtp_host = (smtp_host or "").strip()
        self.smtp_port = int(smtp_port or 587)
        self.auth_mode = (auth_mode or "password").strip().lower()   # "password" | "oauth"
        self.token = token or ""                                     # access token (OAuth) — used with XOAUTH2

    # -- IMAP ------------------------------------------------------------------------------------------------------
    def _imap(self) -> imaplib.IMAP4_SSL:
        im = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=_IMAP_TIMEOUT)
        if self.auth_mode == "oauth":
            # SASL XOAUTH2: imaplib base64-encodes what the authobject returns; return raw SASL bytes.
            im.authenticate("XOAUTH2", lambda _=None: xoauth2_sasl(self.address, self.token).encode())
        else:
            im.login(self.address, self.password)
        return im

    def test_connection(self) -> tuple[bool, str]:
        """Test IMAP+SMTP login. Returns (ok, reason) — to validate the connection when connecting from the UI."""
        cred = ("token", self.token) if self.auth_mode == "oauth" else ("contraseña", self.password)
        missing = [n for n, v in (("dirección", self.address), cred,
                                   ("IMAP host", self.imap_host), ("SMTP host", self.smtp_host)) if not v]
        if missing:
            return False, "falta: " + ", ".join(missing)
        try:
            im = self._imap()
            im.logout()
        except Exception as e:
            return False, f"IMAP: {e}"
        try:
            s = self._connect_smtp()
            try:
                self._smtp_login(s)
            finally:
                s.quit()
        except Exception as e:
            return False, f"SMTP: {e}"
        return True, "ok"
