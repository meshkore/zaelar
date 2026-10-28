"""SMTP: the connection with its IPv4 fallback, the SASL strings both transports authenticate with, and the three
sends. Mixed into `Mailbox`; `_connect_smtp` / `_smtp_login` are what a test stubs to keep the network out."""
import base64
import smtplib
import socket
import ssl
import uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

_SMTP_CONNECT_TIMEOUT = 30


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def xoauth2_sasl(user: str, token: str) -> str:
    """SASL XOAUTH2 string (RFC 7628) for IMAP/SMTP with OAuth2 — Gmail and Outlook use it over the SAME IMAP/SMTP
    transport (the token replaces the password). Format: 'user=<u>^Aauth=Bearer <t>^A^A'. Pure/testable."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


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


def _message_id(address: str) -> str:
    domain = address.split("@")[-1] if "@" in address else "zaelar.local"
    return f"<zaelar-{uuid.uuid4().hex[:12]}@{domain}>"


def _cc_header(cc: list | None, to_addr: str) -> list[str]:
    return [str(a).strip() for a in (cc or []) if str(a).strip() and str(a).strip().lower() != to_addr.lower()]


class _SmtpMixin:
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

    def _deliver(self, msg, mid: str) -> tuple[bool, str]:
        """One connection per send: login, send, quit. Returns (ok, message_id|error)."""
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

    def send_invitation(self, to_addr: str, subject: str, body: str, ics_text: str,
                        method: str = "REQUEST", cc: list | None = None) -> tuple[bool, str]:
        """Send a meeting invitation the recipient's CALENDAR can accept, not a link in a paragraph (V2-718).

        This is the second rung of the ladder described in `connectors/calendar/ics.py`: the first is adding
        the person as a guest on a calendar account we hold, where Google mails the invitation itself. Here
        there is no calendar behind the meeting, so the invitation has to be built and carried by us.

        The SHAPE is what makes a mail an invitation rather than a mail with a file stuck to it, and every
        part of it is load-bearing:

          · `multipart/alternative` holding `text/plain` AND `text/calendar; method=REQUEST` — this is what
            Apple Mail, Outlook and Gmail read to show Accept / Decline inline. A client that understands
            neither still shows the plain text, which is why the text is written to stand alone.
          · the same object AGAIN as an `.ics` attachment, because several clients (older Outlook, most
            webmail on mobile) only offer «add to calendar» from a file.
          · `method=REQUEST` on the Content-Type, not only inside the object: a part typed
            `text/calendar` with no method is treated as a published calendar, which is a different thing
            and shows no buttons at all.

        ⚠️ The ORGANIZER inside `ics_text` must be THIS mailbox. A REQUEST that claims to come from somebody
        else is both the shape spam filters reject and a reply routed to an address nobody is reading.
        """
        to_addr = (to_addr or "").strip()
        if not to_addr:
            return False, "sin destinatario"
        if not str(ics_text or "").strip():
            return False, "sin invitación que mandar"
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body or "", "plain", "utf-8"))
        cal = MIMEText(ics_text, "calendar", "utf-8")
        cal.replace_header("Content-Type", f'text/calendar; charset="utf-8"; method={method}')
        alt.attach(cal)
        msg = MIMEMultipart("mixed")
        msg.attach(alt)
        att = MIMEApplication(ics_text.encode("utf-8"), _subtype="ics", name="invite.ics")
        att.add_header("Content-Disposition", "attachment", filename="invite.ics")
        msg.attach(att)
        msg["From"] = self.address
        msg["To"] = to_addr
        cc_list = _cc_header(cc, to_addr)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject or "Invitación"
        msg["Date"] = formatdate(localtime=True)
        mid = _message_id(self.address)
        msg["Message-ID"] = mid
        return self._deliver(msg, mid)

    def send_message(self, to_addr: str, subject: str, body: str, attachments: list | None = None) -> tuple[bool, str]:
        """A NEW message (no «Re:», no thread) carrying files — what forwarding an invoice to somebody is.

        `attachments` are local paths; each travels with its own filename and a type guessed from it. A path that
        cannot be read fails the send rather than dropping the file in silence: a mail announcing an invoice
        that arrives without it is the failure this exists to avoid. Returns (ok, message_id|error)."""
        from connectors.email import attachments as _att
        to_addr = (to_addr or "").strip()
        if not to_addr:
            return False, "sin destinatario"
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText(body or "", "plain", "utf-8"))
        err = _att.attach(msg, attachments)
        if err:
            return False, err
        msg["From"] = self.address
        msg["To"] = to_addr
        msg["Subject"] = subject or ""
        msg["Date"] = formatdate(localtime=True)
        mid = _message_id(self.address)
        msg["Message-ID"] = mid
        return self._deliver(msg, mid)

    def send_reply(self, to_addr: str, subject: str, body: str, in_reply_to: str = "",
                   cc: list | None = None, attachments: list | None = None) -> tuple[bool, str]:
        """Send a reply by SMTP with correct threading (In-Reply-To/References, subject Re:). Returns
        (ok, message_id|error).

        `cc` (V2-680) is what turns this into a reply-ALL: the other recipients of the original, already
        stripped of the sender and of our own address when they were parsed. Empty or absent means a plain
        reply, byte-for-byte what this method sent before — so no caller that omits it changes behaviour."""
        to_addr = (to_addr or "").strip()
        if not to_addr:
            return False, "sin destinatario"
        subj = subject or ""
        if not subj.lower().startswith("re:"):
            subj = f"Re: {subj}" if subj else "Re:"
        msg = MIMEText(body or "", "plain", "utf-8")
        if attachments:                   # files picked in the card travel with the reply too
            from connectors.email import attachments as _att
            msg = MIMEMultipart("mixed")
            msg.attach(MIMEText(body or "", "plain", "utf-8"))
            if (err := _att.attach(msg, attachments)):
                return False, err
        msg["From"] = self.address
        msg["To"] = to_addr
        # The Cc HEADER is what the recipients see, and `send_message` derives the envelope from To+Cc+Bcc
        # on its own — so there is no second list to keep in sync here.
        cc_list = _cc_header(cc, to_addr)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subj
        msg["Date"] = formatdate(localtime=True)
        mid = _message_id(self.address)
        msg["Message-ID"] = mid
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        return self._deliver(msg, mid)
