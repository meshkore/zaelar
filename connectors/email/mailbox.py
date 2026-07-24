#
# mailbox.py — lógica IMAP/SMTP PURA del conector email (V2-051). VENDORIZADA + adaptada del adaptador de email de
# Hermes (~/.hermes/hermes-agent/plugins/platforms/email/adapter.py), que es stdlib puro (imaplib/smtplib). Aquí NO
# hay asyncio ni bus: son funciones/clase SÍNCRONAS y bloqueantes (el service.py las corre en asyncio.to_thread) y
# 100% testeables sin red (los parsers son puros). No depende de ninguna clase interna de Hermes.
#
# Diferencias con Hermes (a propósito):
#   · Leemos el BUZÓN PROPIO del operador (no aceptamos órdenes de remitentes) → la verificación SPF/DKIM/DMARC es
#     un METADATO de confianza (`authenticated`), NO un gate de autorización.
#   · FETCH con BODY.PEEK[] → NO marca \Seen al leer; marcar leído es una acción EXPLÍCITA del operador (mark_seen).
#   · Dedup por UID de IMAP (estable por buzón) = el `messageId` del store; el Message-ID RFC se guarda aparte
#     (`msgid`) para el threading de la respuesta.
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

# ── Presets de proveedor (host IMAP/SMTP) ────────────────────────────────────────────────────────────────────────
# El REGISTRO ÚNICO de proveedores vive en `providers.py` (V2-055). Aquí se re-exporta el mapa de hosts legacy
# `PRESETS` para compatibilidad con quien lo importaba de este módulo (config.py).
from connectors.email.providers import PRESETS  # noqa: E402,F401  (re-export de compat)


def xoauth2_sasl(user: str, token: str) -> str:
    """String SASL XOAUTH2 (RFC 7628) para IMAP/SMTP con OAuth2 — Gmail y Outlook lo usan sobre el MISMO transporte
    IMAP/SMTP (el token sustituye a la contraseña). Formato: 'user=<u>^Aauth=Bearer <t>^A^A'. Puro/testeable."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01"

# Remitentes automáticos — su correo se ignora en silencio (nunca es un mensaje personal que triar/responder).
_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "notifications@",
    "automated@", "auto-confirm", "auto-reply", "automailer",
)
# Headers RFC que delatan correo masivo/automático.
_AUTOMATED_HEADERS = {
    "Auto-Submitted": lambda v: v.lower() != "no",
    "Precedence": lambda v: v.lower() in {"bulk", "list", "junk"},
    "X-Auto-Response-Suppress": lambda v: bool(v),
    "List-Unsubscribe": lambda v: bool(v),
}

_IMAP_TIMEOUT = 30
_SMTP_CONNECT_TIMEOUT = 30
MAX_BODY_LENGTH = 20_000          # el triaje solo necesita el cuerpo; recortamos correos gigantes


# ── Parsers puros (testeables sin red) ────────────────────────────────────────────────────────────────────────────
def decode_header_value(raw: str) -> str:
    """Decodifica un header RFC 2047 (=?UTF-8?...) a texto plano."""
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
    """Quita tags HTML de forma ingenua (fallback cuando no hay text/plain)."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text_body(msg) -> str:
    """Extrae el cuerpo de texto de un email posiblemente multipart (prefiere text/plain; cae a text/html→texto)."""
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
    """'Nombre <addr@x>' → 'addr@x' (minúsculas)."""
    m = re.search(r"<([^>]+)>", raw or "")
    return (m.group(1) if m else (raw or "")).strip().lower()


def display_name(raw: str, fallback: str) -> str:
    """Nombre visible del remitente ('Nombre <addr>' → 'Nombre'), o el fallback (la dirección)."""
    name = decode_header_value(raw or "")
    if "<" in name:
        name = name.split("<")[0].strip().strip('"')
    return name or fallback


def is_automated_sender(address: str, headers: dict) -> bool:
    """True si el correo es de un remitente automático/noreply o marcado como masivo por headers."""
    addr = (address or "").lower()
    if any(p in addr for p in _NOREPLY_PATTERNS):
        return True
    for header, check in _AUTOMATED_HEADERS.items():
        val = headers.get(header, "")
        if val and check(val):
            return True
    return False


# ── Verificación SPF/DKIM/DMARC (metadato de confianza) ─────────────────────────────────────────────────────────
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
    """¿El dominio del From: está autenticado (SPF/DKIM/DMARC) según el header Authentication-Results que estampa
    NUESTRO servidor receptor? El From: es falsificable; este es el único indicador fiable. Devuelve (ok, motivo).
    Sin header → (False, 'no Authentication-Results') — no bloquea nada, solo marca el metadato."""
    from_domain = _domain_of(from_addr)
    if not from_domain:
        return False, "missing From domain"
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False, "no Authentication-Results header"
    trusted = " ".join(str(headers[0]).split())        # el receptor lo antepone → el PRIMERO es el de confianza
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
    """Un email crudo (RFC822) → dict normalizado para el triaje/store, o None si hay que ignorarlo (automático).
    `uid` = UID de IMAP (str) → se usa como messageId (estable por buzón). El Message-ID RFC va en `msgid`."""
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
        "isGroup": False,                     # el correo personal es 1:1 (el hilo es el "chat")
        "chatName": None,
        "body": (f"[Asunto: {subject}]\n{body}" if subject and not subject.startswith("Re:") else body) or "(vacío)",
        "messageId": str(uid),                # UID de IMAP → dedup + mark-seen
        "chatId": from_addr,                  # el remitente ES el hilo/chat
        "senderId": from_addr,
        "subject": subject,
        "msgid": msg.get("Message-ID", ""),   # Message-ID RFC → threading de la respuesta
        "authenticated": authok,
        "auth_reason": why,
    }


# ── SMTP con IPv4-fallback (redes sin ruta IPv6 cuelgan hasta el timeout) ────────────────────────────────────────
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


# ── El buzón: conexión + operaciones (bloqueantes; el service las corre en to_thread) ────────────────────────────
class Mailbox:
    """Conexión IMAP (leer) + SMTP (enviar). Sin estado de red persistente: cada operación abre/cierra su conexión
    (robusto ante caídas de red; el poll es cada N s, no una conexión IDLE viva)."""

    def __init__(self, address: str, password: str, imap_host: str, imap_port: int,
                 smtp_host: str, smtp_port: int, auth_mode: str = "password", token: str = ""):
        self.address = (address or "").strip()
        self.password = password or ""
        self.imap_host = (imap_host or "").strip()
        self.imap_port = int(imap_port or 993)
        self.smtp_host = (smtp_host or "").strip()
        self.smtp_port = int(smtp_port or 587)
        self.auth_mode = (auth_mode or "password").strip().lower()   # "password" | "oauth"
        self.token = token or ""                                     # access token (OAuth) — usado con XOAUTH2

    # -- IMAP ------------------------------------------------------------------------------------------------------
    def _imap(self) -> imaplib.IMAP4_SSL:
        im = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=_IMAP_TIMEOUT)
        if self.auth_mode == "oauth":
            # SASL XOAUTH2: imaplib base64-codifica lo que devuelve el authobject; devolvemos la SASL cruda en bytes.
            im.authenticate("XOAUTH2", lambda _=None: xoauth2_sasl(self.address, self.token).encode())
        else:
            im.login(self.address, self.password)
        return im

    def _smtp_login(self, s: smtplib.SMTP) -> None:
        """Autentica una conexión SMTP ya establecida: password o XOAUTH2 (OAuth)."""
        if self.auth_mode == "oauth":
            s.ehlo()
            sasl = xoauth2_sasl(self.address, self.token).encode()
            code, resp = s.docmd("AUTH", "XOAUTH2 " + _b64(sasl))
            if code not in (235, 334):
                raise smtplib.SMTPAuthenticationError(code, resp)
        else:
            s.login(self.address, self.password)

    def test_connection(self) -> tuple[bool, str]:
        """Prueba IMAP+SMTP login. Devuelve (ok, motivo) — para validar la conexión al conectar desde la UI."""
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
        """Todos los UID actuales de INBOX (para sembrar el `seen` al conectar → solo triamos correo NUEVO)."""
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
        """Devuelve los correos de INBOX cuyo UID no está en `seen`, parseados y normalizados (sin marcar \\Seen —
        usa BODY.PEEK). NO muta `seen` (lo hace el llamante tras publicar). Nunca lanza hacia arriba."""
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
        """Marca \\Seen (leído en el servidor) los UID dados. True si OK (best-effort en lote)."""
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
            return _do(ipv4=True)          # reintento IPv4 (IPv6 inalcanzable)

    def send_reply(self, to_addr: str, subject: str, body: str, in_reply_to: str = "") -> tuple[bool, str]:
        """Envía una respuesta por SMTP con threading correcto (In-Reply-To/References, Re: del asunto).
        Devuelve (ok, message_id|error)."""
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
