#
# providers.py — SINGLE cloud-file-provider registry (V2-557). The product's "file connector list": one entry
# per provider with its OAuth2 config, its API base and — the part that decides whether this connector can
# BROWSE at all — its SCOPE TIERS. Consumed by `oauth.py` (endpoints/scopes), `service.py` (which client to
# call), the registry (`connectors/registry.py`), the ⚙ Connectors tab and the tests. One source of truth so
# the layers cannot diverge, exactly like `connectors/email/providers.py` (V2-055) does for mail.
#
# ── THE SCOPE TIER IS THE WHOLE DESIGN, so it is a first-class field and not a constant ──────────────────────
#
# A file browser is only as good as what the token is allowed to SEE, and the two providers are not in the same
# situation. Stated as mechanism (what the API does), never as product policy (what we may ship) — that half
# lives in the workspace's private repo:
#
#   · Google Drive has TWO tiers and they are not interchangeable:
#       - `drive.file`     — the app sees ONLY files it created itself or that the user hand-picked through
#                            Google's own Picker. NOT a restricted scope, so an app carrying just this one
#                            needs no CASA security assessment. It also means there is NO TREE TO BROWSE: a
#                            fresh install shows an empty root, and that is correct behaviour, not a bug.
#       - `drive.readonly` — the real browse: every file and folder, read-only. This IS a restricted scope.
#                            Google requires a CASA assessment before a PUBLISHED app may ask for it; an
#                            operator using THEIR OWN OAuth client with themselves as a test user is not
#                            publishing anything and is not subject to it. That distinction is why this is a
#                            per-installation choice and not a hardcoded constant.
#   · Microsoft Graph asks for no equivalent assessment for personal OneDrive: `Files.Read` browses, and
#     `offline_access` is what makes the refresh token exist at all. One tier, so `tiers` has one entry — the
#     field is not Google-specific plumbing leaking into every provider.
#
# Adding a provider = one entry in PROVIDERS + one client module. Nothing else in the system knows their names.
#
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeTier:
    """One coherent set of OAuth scopes, with what it actually buys. `browsable` is the field the widget and
    the connect form read: False means the provider will answer, correctly, with an empty tree until the
    operator hands it individual files."""
    id: str
    label: str
    scopes: tuple[str, ...]
    browsable: bool
    note: str = ""


@dataclass(frozen=True)
class FilesProvider:
    id: str
    label: str
    authorize_url: str
    token_url: str
    api_base: str
    tiers: tuple[ScopeTier, ...]
    default_tier: str
    # A Microsoft "web" app registration requires a client secret; a Google installed app with PKCE does not.
    needs_client_secret: bool = False
    # Extra params the authorize URL needs for a refresh token to come back at all. Google wants
    # `access_type=offline` + `prompt=consent`; Microsoft gets the same effect from the `offline_access` scope.
    extra_auth_params: dict = field(default_factory=dict)
    note: str = ""

    def tier(self, tier_id: str = "") -> ScopeTier:
        """The named tier, or the default. Never raises — an unknown id from a stale config falls back rather
        than taking the connector down."""
        wanted = (tier_id or "").strip() or self.default_tier
        for t in self.tiers:
            if t.id == wanted:
                return t
        for t in self.tiers:
            if t.id == self.default_tier:
                return t
        return self.tiers[0]


_GOOGLE_TIERS = (
    ScopeTier(
        id="browse", label="Ver todo mi Drive (solo lectura)",
        scopes=("https://www.googleapis.com/auth/drive.readonly",),
        browsable=True,
        note="Permite navegar por todas tus carpetas. Google lo considera un permiso restringido: con tu "
             "propia app de Google Cloud y tu cuenta como usuario de prueba funciona sin trámites."),
    ScopeTier(
        id="picked", label="Solo los archivos que yo elija",
        scopes=("https://www.googleapis.com/auth/drive.file",),
        browsable=False,
        note="El permiso más estrecho: zaelar solo ve los archivos que le entregues expresamente. No podrá "
             "listar tus carpetas."),
)

PROVIDERS: dict[str, FilesProvider] = {
    "gdrive": FilesProvider(
        id="gdrive", label="Google Drive",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        api_base="https://www.googleapis.com/drive/v3",
        tiers=_GOOGLE_TIERS, default_tier="browse",
        needs_client_secret=False,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
        note="Necesita una app OAuth propia en Google Cloud (una vez). Elige qué permiso le das."),
    "onedrive": FilesProvider(
        id="onedrive", label="OneDrive",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        api_base="https://graph.microsoft.com/v1.0",
        tiers=(ScopeTier(id="browse", label="Ver mis archivos de OneDrive (solo lectura)",
                         scopes=("Files.Read", "offline_access", "openid", "email"),
                         browsable=True,
                         note="Permiso normal de Microsoft Graph: no exige auditoría para OneDrive personal."),),
        default_tier="browse",
        needs_client_secret=False,
        note="Necesita registrar una app en Microsoft Entra (una vez), de tipo pública/nativa."),
}


def get(provider_id: str) -> FilesProvider | None:
    return PROVIDERS.get((provider_id or "").strip().lower())


def ids() -> list[str]:
    return list(PROVIDERS.keys())


def public_list() -> list[dict]:
    """Redacted list for the frontend connect form: id, label, note and the tiers with what each one buys.
    No endpoints, no credentials — the same contract as `email.providers.public_list()`."""
    out = []
    for p in PROVIDERS.values():
        out.append({
            "id": p.id, "label": p.label, "note": p.note, "default_tier": p.default_tier,
            "tiers": [{"id": t.id, "label": t.label, "browsable": t.browsable, "note": t.note}
                      for t in p.tiers],
        })
    return out
