#
# providers.py — SINGLE email-provider registry (V2-055). The product's "email connector list": one entry per
# provider with its IMAP/SMTP servers + supported AUTHENTICATION METHODS + (if applicable) OAuth2 config. Consumed
# by config.py (resolve hosts + method), the widget (render channel list), the OAuth seam (endpoints/scopes), and
# tests. One source of truth → layers do not diverge.
#
# AUTHENTICATION METHODS:
#   · "password"  — IMAP/SMTP with application password (app-password). Simple, no app registration. Gmail allows it
#                   with 2FA; Yahoo/iCloud too. **Microsoft DEPRECATED basic-auth** (Sept 2024) → Outlook does NOT
#                   accept password, ONLY oauth.
#   · "oauth"     — OAuth2 (authorization-code). Transport remains IMAP/SMTP but with **SASL XOAUTH2** (token
#                   instead of password) → reuses `mailbox.py`. Requires registering an app (Google Cloud /
#                   Microsoft Entra) ONCE; then the user connects with "sign in with Google/Microsoft".
#
# `auth_methods` order is PREFERENCE (the first one is recommended for that provider).
#
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthSpec:
    """Provider OAuth2 config (authorization-code). Public endpoints; the operator sets client_id/secret in the
    credential store (dormant until then, like Spotify V2-041)."""
    authority: str                 # base del proveedor de identidad
    authorize_url: str             # authorization endpoint (consent)
    token_url: str                 # endpoint de intercambio/refresh de token
    scopes: tuple[str, ...]        # minimal scopes to read + send email (IMAP/SMTP XOAUTH2)
    pkce: bool = True              # PKCE S256 (recommended; Google/Microsoft support it for installed apps)
    needs_client_secret: bool = False   # Microsoft "web" app exige secret; Google instalada/PKCE no


@dataclass(frozen=True)
class EmailProvider:
    id: str
    label: str
    imap_host: str
    smtp_host: str
    imap_port: int = 993
    smtp_port: int = 587
    auth_methods: tuple[str, ...] = ("password",)
    oauth: OAuthSpec | None = None
    domains: tuple[str, ...] = field(default_factory=tuple)   # domains that infer this provider
    note: str = ""

    def supports(self, method: str) -> bool:
        return method in self.auth_methods

    @property
    def default_method(self) -> str:
        return self.auth_methods[0] if self.auth_methods else "password"


# Scopes: use IMAP/SMTP transport with XOAUTH2 (reuses mailbox.py), not REST APIs → scopes are "full mail": Google
# `https://mail.google.com/` (IMAP+SMTP), Microsoft IMAP/SMTP + offline_access (refresh).
_GOOGLE_OAUTH = OAuthSpec(
    authority="https://accounts.google.com",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=("https://mail.google.com/",),
    pkce=True,
    needs_client_secret=False,
)
_MICROSOFT_OAUTH = OAuthSpec(
    authority="https://login.microsoftonline.com/common",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    # Delegated IMAP/SMTP + offline_access (refresh token) + openid/email (identity). Microsoft requires the
    # https://outlook.office.com/ prefix for XOAUTH2 mail scopes.
    scopes=("https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/SMTP.Send",
            "offline_access", "openid", "email"),
    pkce=True,
    needs_client_secret=False,     # app "public/native" en Entra → PKCE sin secret
)

# ── THE LIST (all product email connectors) ───────────────────────────────────────────────────────────────────
PROVIDERS: dict[str, EmailProvider] = {
    "gmail": EmailProvider(
        id="gmail", label="Gmail", imap_host="imap.gmail.com", smtp_host="smtp.gmail.com",
        auth_methods=("oauth", "password"), oauth=_GOOGLE_OAUTH,
        domains=("gmail.com", "googlemail.com"),
        note="OAuth (recomendado, 'iniciar sesión con Google') o app-password con 2FA."),
    "outlook": EmailProvider(
        id="outlook", label="Outlook / Microsoft 365", imap_host="outlook.office365.com",
        smtp_host="smtp-mail.outlook.com", auth_methods=("oauth",), oauth=_MICROSOFT_OAUTH,
        domains=("outlook.com", "hotmail.com", "live.com", "msn.com", "office365.com"),
        note="SOLO OAuth: Microsoft deshabilitó la contraseña básica (basic-auth) en IMAP/SMTP."),
    "yahoo": EmailProvider(
        id="yahoo", label="Yahoo Mail", imap_host="imap.mail.yahoo.com", smtp_host="smtp.mail.yahoo.com",
        auth_methods=("password",), domains=("yahoo.com", "ymail.com"),
        note="App-password (genera una 'contraseña de aplicación' en la seguridad de Yahoo)."),
    "icloud": EmailProvider(
        id="icloud", label="iCloud Mail", imap_host="imap.mail.me.com", smtp_host="smtp.mail.me.com",
        auth_methods=("password",), domains=("icloud.com", "me.com", "mac.com"),
        note="App-specific password (appleid.apple.com → Seguridad)."),
    "imap": EmailProvider(
        id="imap", label="Otro (IMAP/SMTP)", imap_host="", smtp_host="",
        auth_methods=("password",),
        note="Cualquier proveedor IMAP/SMTP (Fastmail, ProtonMail Bridge, corporativo…): host + app-password."),
}

# Alias legacy (V2-051 usaba mailbox.PRESETS = {id: {imap_host, imap_port, smtp_host, smtp_port}}).
PRESETS = {pid: {"imap_host": p.imap_host, "imap_port": p.imap_port,
                 "smtp_host": p.smtp_host, "smtp_port": p.smtp_port}
           for pid, p in PROVIDERS.items() if p.imap_host}


def get(provider_id: str) -> EmailProvider | None:
    return PROVIDERS.get((provider_id or "").strip().lower())


def by_domain(address: str) -> EmailProvider | None:
    """Infer provider from the address domain (for 'other'/empty mode)."""
    domain = (address or "").split("@")[-1].strip().lower()
    if not domain:
        return None
    for p in PROVIDERS.values():
        if any(domain == d or domain.endswith("." + d) for d in p.domains):
            return p
    return None


def public_list() -> list[dict]:
    """Redacted list for the frontend (the widget renders 'Available channels'): id, label, methods, note. NO
    endpoints or secrets."""
    out = []
    for p in PROVIDERS.values():
        out.append({"id": p.id, "label": p.label, "auth_methods": list(p.auth_methods),
                    "oauth": bool(p.oauth), "needs_hosts": not p.imap_host, "note": p.note})
    return out
