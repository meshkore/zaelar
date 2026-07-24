#
# config.py — knobs del conector Email (V2-051). Config MANEJADA POR LA INTERFAZ: el store (config/connectors.py,
# escrito por el widget de mensajería) MANDA; `.env` es fallback de power-user / back-compat. Email = IMAP/SMTP con
# app-password (Gmail/Outlook exigen 2FA + app-password). OAuth2 (XOAUTH2) = Fase 2 futura (costura abierta).
#
# El triaje es el compartido (connectors/messaging/triage.py), LOCAL por defecto → nada personal sale de la máquina.
#
import os

from config import connectors as _store            # store gana sobre .env

from connectors.email.mailbox import PRESETS


def enabled() -> bool:
    return _store.enabled("email")


def _cfg() -> dict:
    return _store.get("email")


def address() -> str:
    return str(_cfg().get("email_address") or os.getenv("EMAIL_ADDRESS") or "").strip()


def password() -> str:
    return str(_cfg().get("email_password") or os.getenv("EMAIL_PASSWORD") or "")


def provider() -> str:
    """Preset elegido en la UI (gmail|outlook|icloud|yahoo|otro). '' = deducir del dominio, luego 'otro'."""
    return str(_cfg().get("provider") or "").strip().lower()


def _preset() -> dict:
    """Hosts del preset: primero el `provider` elegido, luego deducido del dominio de la dirección."""
    p = provider()
    if p in PRESETS:
        return PRESETS[p]
    domain = address().split("@")[-1].lower() if "@" in address() else ""
    for name, hosts in PRESETS.items():
        if domain and (domain == hosts["imap_host"].split(".", 1)[-1] or name in domain):
            return hosts
    if "gmail" in domain or "googlemail" in domain:
        return PRESETS["gmail"]
    if any(x in domain for x in ("outlook", "hotmail", "live", "office365")):
        return PRESETS["outlook"]
    if "icloud" in domain or "me.com" in domain:
        return PRESETS["icloud"]
    if "yahoo" in domain:
        return PRESETS["yahoo"]
    return {}


def imap_host() -> str:
    return str(_cfg().get("imap_host") or os.getenv("EMAIL_IMAP_HOST") or _preset().get("imap_host") or "").strip()


def imap_port() -> int:
    return int(_cfg().get("imap_port") or os.getenv("EMAIL_IMAP_PORT") or _preset().get("imap_port") or 993)


def smtp_host() -> str:
    return str(_cfg().get("smtp_host") or os.getenv("EMAIL_SMTP_HOST") or _preset().get("smtp_host") or "").strip()


def smtp_port() -> int:
    return int(_cfg().get("smtp_port") or os.getenv("EMAIL_SMTP_PORT") or _preset().get("smtp_port") or 587)


def resolved_provider_id() -> str:
    """El id de proveedor efectivo (el elegido en la UI, o deducido por el dominio de la dirección, o 'imap')."""
    from connectors.email import providers as pv
    p = provider()
    if pv.get(p):
        return p
    dp = pv.by_domain(address())
    return dp.id if dp else "imap"


def auth_method() -> str:
    """'oauth' si el proveedor lo soporta Y hay app registrada Y tokens de esta cuenta; si no, 'password'."""
    from connectors.email import oauth, providers as pv
    pid = resolved_provider_id()
    prov = pv.get(pid)
    if prov and prov.supports("oauth") and oauth.configured(pid) and oauth.tokens_present(pid, address()):
        return "oauth"
    return "password"


def has_credentials() -> bool:
    if auth_method() == "oauth":
        return bool(address() and imap_host() and smtp_host())     # el token lo aporta el seam OAuth
    return bool(address() and password() and imap_host() and smtp_host())


def autoreply() -> bool:
    """Auto-respuesta automática — DIFERIDA, OFF por defecto (V2-051). Placeholder de opción futura."""
    v = _cfg().get("autoreply")
    if v is not None:
        return bool(v)
    return os.getenv("EMAIL_AUTOREPLY", "0") == "1"


def poll_interval() -> float:
    return float(os.getenv("EMAIL_POLL_INTERVAL", "20"))


def operator_name() -> str:
    return (os.getenv("EMAIL_MY_NAME") or os.getenv("MSG_MY_NAME") or "").strip()


def mailbox():
    """Instancia Mailbox con la config efectiva (o None si faltan credenciales). Elige el modo de auth: OAuth
    (XOAUTH2 con access token vivo) o app-password, según `auth_method()`."""
    if not has_credentials():
        return None
    from connectors.email.mailbox import Mailbox
    if auth_method() == "oauth":
        from connectors.email import oauth
        token = oauth.access_token(resolved_provider_id(), address())
        if not token:
            return None
        return Mailbox(address(), "", imap_host(), imap_port(), smtp_host(), smtp_port(),
                       auth_mode="oauth", token=token)
    return Mailbox(address(), password(), imap_host(), imap_port(), smtp_host(), smtp_port())
