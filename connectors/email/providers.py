#
# providers.py — REGISTRO ÚNICO de proveedores de email (V2-055). La "lista de conectores de email" del producto:
# una entrada por proveedor con sus servidores IMAP/SMTP + los MÉTODOS DE AUTENTICACIÓN que soporta + (si aplica)
# su configuración OAuth2. Lo consumen config.py (resolver hosts + método), el widget (pintar la lista de canales),
# el seam OAuth (endpoints/scopes) y los tests. Una sola fuente de verdad → las capas no divergen.
#
# MÉTODOS DE AUTENTICACIÓN:
#   · "password"  — IMAP/SMTP con contraseña de aplicación (app-password). Simple, sin registrar app. Gmail lo
#                   permite con 2FA; Yahoo/iCloud igual. **Microsoft DEPRECÓ basic-auth** (sept-2024) → Outlook NO
#                   admite password, SOLO oauth.
#   · "oauth"     — OAuth2 (authorization-code). El transporte sigue siendo IMAP/SMTP pero con **SASL XOAUTH2**
#                   (token en vez de contraseña) → reusa `mailbox.py`. Necesita registrar una app (Google Cloud /
#                   Microsoft Entra) UNA vez; luego el usuario conecta con "iniciar sesión con Google/Microsoft".
#
# El orden de `auth_methods` es la PREFERENCIA (el primero es el recomendado para ese proveedor).
#
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthSpec:
    """Config OAuth2 (authorization-code) de un proveedor. Endpoints públicos; el client_id/secret los pone el
    operador en el credential store (dormante hasta entonces, como Spotify V2-041)."""
    authority: str                 # base del proveedor de identidad
    authorize_url: str             # endpoint de autorización (consent)
    token_url: str                 # endpoint de intercambio/refresh de token
    scopes: tuple[str, ...]        # scopes mínimos para leer + enviar correo (IMAP/SMTP XOAUTH2)
    pkce: bool = True              # PKCE S256 (recomendado; Google/Microsoft lo soportan para apps instaladas)
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
    domains: tuple[str, ...] = field(default_factory=tuple)   # dominios que deducen este proveedor
    note: str = ""

    def supports(self, method: str) -> bool:
        return method in self.auth_methods

    @property
    def default_method(self) -> str:
        return self.auth_methods[0] if self.auth_methods else "password"


# Scopes: usamos el transporte IMAP/SMTP con XOAUTH2 (reusa mailbox.py), no las APIs REST → los scopes son los de
# "correo completo": Google `https://mail.google.com/` (IMAP+SMTP), Microsoft IMAP/SMTP + offline_access (refresh).
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
    # IMAP/SMTP delegados + offline_access (refresh token) + openid/email (identidad). Microsoft exige el prefijo
    # https://outlook.office.com/ para los scopes de correo por XOAUTH2.
    scopes=("https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/SMTP.Send",
            "offline_access", "openid", "email"),
    pkce=True,
    needs_client_secret=False,     # app "public/native" en Entra → PKCE sin secret
)

# ── LA LISTA (todos los conectores de email del producto) ─────────────────────────────────────────────────────
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
    """Deduce el proveedor por el dominio de la dirección (para el modo 'otro'/vacío)."""
    domain = (address or "").split("@")[-1].strip().lower()
    if not domain:
        return None
    for p in PROVIDERS.values():
        if any(domain == d or domain.endswith("." + d) for d in p.domains):
            return p
    return None


def public_list() -> list[dict]:
    """Lista redactada para el frontend (el widget pinta 'Canales disponibles'): id, label, métodos, nota. SIN
    endpoints ni secretos."""
    out = []
    for p in PROVIDERS.values():
        out.append({"id": p.id, "label": p.label, "auth_methods": list(p.auth_methods),
                    "oauth": bool(p.oauth), "needs_hosts": not p.imap_host, "note": p.note})
    return out
