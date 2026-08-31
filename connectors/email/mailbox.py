#
# mailbox.py — PURE IMAP/SMTP logic for the email connector (V2-051). VENDORED + adapted from Hermes' email adapter
# (~/.hermes/hermes-agent/plugins/platforms/email/adapter.py), which is pure stdlib (imaplib/smtplib). There is NO
# asyncio or bus here: these are SYNCHRONOUS and blocking functions/classes (service.py runs them in
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
import base64
import email as email_lib
import imaplib
import re
import smtplib
import socket
import ssl
import uuid


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import formatdate

# ── Provider presets (IMAP/SMTP host) ───────────────────────────────────────────────────────────────────────────
# The SINGLE provider registry lives in `providers.py` (V2-055). Here we re-export the legacy hosts map `PRESETS`
# for compatibility with callers that imported it from this module (config.py).
from connectors.email.providers import PRESETS  # noqa: E402,F401  (compatibility re-export)


def xoauth2_sasl(user: str, token: str) -> str:
    """SASL XOAUTH2 string (RFC 7628) for IMAP/SMTP with OAuth2 — Gmail and Outlook use it over the SAME IMAP/SMTP
    transport (the token replaces the password). Format: 'user=<u>^Aauth=Bearer <t>^A^A'. Pure/testable."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01"

# Automatic senders — their mail is silently ignored (never a personal message to triage/reply to).
_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "notifications@",
    "automated@", "auto-confirm", "auto-reply", "automailer",
)
# RFC headers that reveal bulk/automatic email.
_AUTOMATED_HEADERS = {
    "Auto-Submitted": lambda v: v.lower() != "no",
    "Precedence": lambda v: v.lower() in {"bulk", "list", "junk"},
    "X-Auto-Response-Suppress": lambda v: bool(v),
    "List-Unsubscribe": lambda v: bool(v),
}

_IMAP_TIMEOUT = 30
_SMTP_CONNECT_TIMEOUT = 30
MAX_BODY_LENGTH = 20_000          # triage only needs the body; trim huge emails


# ── Pure parsers (testable without network) ─────────────────────────────────────────────────────────────────────
def decode_header_value(raw: str) -> str:
    """Decode an RFC 2047 header (=?UTF-8?...) to plain text."""
    if not raw:
        return ""
    out = []
    for part, charset in decode_header(raw):
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join(out)


def strip_html(html: str) -> str:
    """Naively remove HTML tags (fallback when text/plain is missing)."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text_body(msg) -> str:
    """Extract the text body from a possibly multipart email (prefer text/plain; fall back to text/html→text)."""
    if msg.is_multipart():
        for want_html in (False, True):
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    continue
                ctype = part.get_content_type()
                if (ctype == "text/html") != want_html:
                    continue
                if ctype not in ("text/plain", "text/html"):
                    continue
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    txt = payload.decode(charset, errors="replace")
                    return strip_html(txt) if want_html else txt
        return ""
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    txt = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return strip_html(txt) if msg.get_content_type() == "text/html" else txt


def extract_email_address(raw: str) -> str:
    """'Name <addr@x>' → 'addr@x' (lowercase)."""
    m = re.search(r"<([^>]+)>", raw or "")
    return (m.group(1) if m else (raw or "")).strip().lower()


def display_name(raw: str, fallback: str) -> str:
    """Visible sender name ('Name <addr>' → 'Name'), or fallback (the address)."""
    name = decode_header_value(raw or "")
    if "<" in name:
        name = name.split("<")[0].strip().strip('"')
    return name or fallback


def is_automated_sender(address: str, headers: dict) -> bool:
    """True if the email comes from an automatic/noreply sender or is marked as bulk by headers."""
    addr = (address or "").lower()
    if any(p in addr for p in _NOREPLY_PATTERNS):
        return True
    for header, check in _AUTOMATED_HEADERS.items():
        val = headers.get(header, "")
        if val and check(val):
            return True
    return False


# ── SPF/DKIM/DMARC verification (trust metadata) ────────────────────────────────────────────────────────────────
def _domain_of(address: str) -> str:
    _, _, domain = (address or "").rpartition("@")
    return domain.strip().lower()


def _domains_aligned(a: str, b: str) -> bool:
    a = (a or "").strip().lower().rstrip(".")
    b = (b or "").strip().lower().rstrip(".")
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


_AUTH_METHOD_RE = re.compile(r"\b(dmarc|dkim|spf)\s*=\s*([a-z]+)", re.IGNORECASE)
_AUTH_PROP_RE = re.compile(
    r"\b(header\.from|header\.d|smtp\.mailfrom|smtp\.from|envelope-from)\s*=\s*([^\s;]+)", re.IGNORECASE)


def verify_sender_authentication(msg, from_addr: str) -> tuple[bool, str]:
    """Is the From: domain authenticated (SPF/DKIM/DMARC) according to the Authentication-Results header stamped by
    OUR receiving server? From: is forgeable; this is the only reliable indicator. Returns (ok, reason). Missing
    header → (False, 'no Authentication-Results') — blocks nothing, only marks metadata."""
    from_domain = _domain_of(from_addr)
    if not from_domain:
        return False, "missing From domain"
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False, "no Authentication-Results header"
    trusted = " ".join(str(headers[0]).split())        # receiver prepends it → FIRST one is trusted
    methods = {m.lower(): r.lower() for m, r in _AUTH_METHOD_RE.findall(trusted)}
    props = {p.lower(): v.strip().strip('"') for p, v in _AUTH_PROP_RE.findall(trusted)}
    if methods.get("dmarc") == "pass":
        return True, "dmarc=pass"
    if methods.get("spf") == "pass":
        spf = props.get("smtp.mailfrom") or props.get("smtp.from") or props.get("envelope-from") or ""
        if _domains_aligned(_domain_of(spf) if "@" in spf else spf, from_domain):
            return True, "spf=pass aligned"
    if methods.get("dkim") == "pass":
        dkim = props.get("header.d") or _domain_of(props.get("header.from", ""))
        if _domains_aligned(dkim, from_domain):
            return True, "dkim=pass aligned"
    return False, f"unauthenticated ({trusted[:80]})"


def parse_message(uid: str, raw_bytes: bytes) -> dict | None:
    """Raw email (RFC822) → normalized dict for triage/store, or None if it should be ignored (automatic).
    `uid` = IMAP UID (str) → used as messageId (stable per mailbox). RFC Message-ID goes in `msgid`."""
    msg = email_lib.message_from_bytes(raw_bytes)
    from_raw = msg.get("From", "")
    from_addr = extract_email_address(from_raw)
    headers = dict(msg.items())
    if is_automated_sender(from_addr, headers):
        return None
    subject = decode_header_value(msg.get("Subject", "(sin asunto)"))
    body = (extract_text_body(msg) or "").strip()[:MAX_BODY_LENGTH]
    authok, why = verify_sender_authentication(msg, from_addr)
    return {
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
    }


# ── SMTP with IPv4 fallback (networks without IPv6 route hang until timeout) ────────────────────────────────────
def _ipv4_connection(host: str, port: int, timeout: float):
    last = None
    for family, socktype, proto, _c, sockaddr in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            last = e
            sock.close()
    raise last or OSError(f"sin IPv4 para {host}:{port}")


class _IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):            # noqa: D401
        return _ipv4_connection(host, port, timeout)


class _IPv4SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):            # noqa: D401
        return self.context.wrap_socket(_ipv4_connection(host, port, timeout),
                                        server_hostname=getattr(self, "_host", host))


# ── The mailbox: connection + operations (blocking; service runs them in to_thread) ─────────────────────────────
class Mailbox:
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

    def _smtp_login(self, s: smtplib.SMTP) -> None:
        """Authenticate an already-established SMTP connection: password or XOAUTH2 (OAuth)."""
        if self.auth_mode == "oauth":
            s.ehlo()
            sasl = xoauth2_sasl(self.address, self.token).encode()
            code, resp = s.docmd("AUTH", "XOAUTH2 " + _b64(sasl))
            if code not in (235, 334):
                raise smtplib.SMTPAuthenticationError(code, resp)
        else:
            s.login(self.address, self.password)

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

    def all_uids(self) -> set[str]:
        """All current INBOX UIDs (to seed `seen` on connect → only triage NEW mail)."""
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

    def fetch_new(self, seen: set[str]) -> list[dict]:
        """Return INBOX emails whose UID is not in `seen`, parsed and normalized (without marking \\Seen — uses
        BODY.PEEK). Does NOT mutate `seen` (caller does it after publishing). Never raises upward."""
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
                st, msg_data = im.uid("fetch", uid, "(BODY.PEEK[])")
                if st != "OK" or not msg_data or not msg_data[0]:
                    continue
                try:
                    parsed = parse_message(uid, msg_data[0][1])
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

    def mark_seen(self, uids: list[str]) -> bool:
        """Mark the given UIDs as \\Seen (read on the server). True if OK (batch best-effort)."""
        uids = [u for u in (uids or []) if u]
        if not uids:
            return True
        try:
            im = self._imap()
            try:
                im.select("INBOX")
                for uid in uids:
                    try:
                        im.uid("store", uid, "+FLAGS", "(\\Seen)")
                    except Exception:
                        pass
            finally:
                im.logout()
            return True
        except Exception:
            return False

    # -- SMTP ------------------------------------------------------------------------------------------------------
    def _connect_smtp(self) -> smtplib.SMTP:
        ctx = ssl.create_default_context()

        def _do(ipv4: bool):
            if self.smtp_port == 465:
                cls = _IPv4SMTP_SSL if ipv4 else smtplib.SMTP_SSL
                return cls(self.smtp_host, self.smtp_port, timeout=_SMTP_CONNECT_TIMEOUT, context=ctx)
            cls = _IPv4SMTP if ipv4 else smtplib.SMTP
            s = cls(self.smtp_host, self.smtp_port, timeout=_SMTP_CONNECT_TIMEOUT)
            try:
                s.starttls(context=ctx)
            except Exception:
                s.close()
                raise
            return s
        try:
            return _do(ipv4=False)
        except ssl.SSLError:
            raise
        except (socket.timeout, TimeoutError, ConnectionError, OSError):
            return _do(ipv4=True)          # IPv4 retry (unreachable IPv6)

    def send_reply(self, to_addr: str, subject: str, body: str, in_reply_to: str = "") -> tuple[bool, str]:
        """Send a reply by SMTP with correct threading (In-Reply-To/References, subject Re:). Returns
        (ok, message_id|error)."""
        to_addr = (to_addr or "").strip()
        if not to_addr:
            return False, "sin destinatario"
        subj = subject or ""
        if not subj.lower().startswith("re:"):
            subj = f"Re: {subj}" if subj else "Re:"
        msg = MIMEText(body or "", "plain", "utf-8")
        msg["From"] = self.address
        msg["To"] = to_addr
        msg["Subject"] = subj
        msg["Date"] = formatdate(localtime=True)
        domain = self.address.split("@")[-1] if "@" in self.address else "zaelar.local"
        mid = f"<zaelar-{uuid.uuid4().hex[:12]}@{domain}>"
        msg["Message-ID"] = mid
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        try:
            s = self._connect_smtp()
            try:
                self._smtp_login(s)
                s.send_message(msg)
            finally:
                try:
                    s.quit()
                except Exception:
                    s.close()
            return True, mid
        except Exception as e:
            return False, str(e)
