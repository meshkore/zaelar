#
# providers.py — SINGLE photo-provider registry (V2-564). Same shape as `connectors/files/providers.py`
# (V2-557) on purpose — a Google Photos connector is the same KIND of problem (OAuth + a provider that only
# shows what it is allowed to), so it reuses the pattern rather than inventing a second one.
#
# ── WHY THIS IS A PICKER, NOT A BROWSER — read before touching anything OAuth here ────────────────────────
#
# Google shut off third-party read access to a user's EXISTING Google Photos library in March 2025: the old
# `photoslibrary.readonly` scope now answers every call with a 403. The only surface left for a third-party
# app is the Picker API — the user opens GOOGLE'S OWN picker UI in a new tab, hand-selects items or albums for
# ONE session, and the app receives exactly those items and nothing else. There is no tier here that "browses
# everything" the way Drive's `drive.readonly` does; `browsable=False` is not a narrower option, it is the
# ONLY option, and it is why `service.py` keeps an independent local index (`store.py`) instead of treating
# Google as a live source of truth the way `connectors/files/service.py` treats Drive.
#
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeTier:
    id: str
    label: str
    scopes: tuple[str, ...]
    browsable: bool
    note: str = ""


@dataclass(frozen=True)
class PhotosProvider:
    id: str
    label: str
    authorize_url: str
    token_url: str
    api_base: str
    tiers: tuple[ScopeTier, ...]
    default_tier: str
    needs_client_secret: bool = False
    extra_auth_params: dict = field(default_factory=dict)
    note: str = ""

    def tier(self, tier_id: str = "") -> ScopeTier:
        wanted = (tier_id or "").strip() or self.default_tier
        for t in self.tiers:
            if t.id == wanted:
                return t
        for t in self.tiers:
            if t.id == self.default_tier:
                return t
        return self.tiers[0]


_GOOGLE_PHOTOS_TIERS = (
    ScopeTier(
        id="picked", label="Solo las fotos que yo elija",
        scopes=("https://www.googleapis.com/auth/photospicker.mediaitems.readonly",),
        browsable=False,
        note="El único permiso que Google ofrece hoy a apps externas: eliges tus fotos en el selector de "
             "Google, una tanda cada vez. No hay «ver toda mi biblioteca»."),
)

PROVIDERS: dict[str, PhotosProvider] = {
    "google-photos": PhotosProvider(
        id="google-photos", label="Google Photos",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        api_base="https://photospicker.googleapis.com/v1",
        tiers=_GOOGLE_PHOTOS_TIERS, default_tier="picked",
        needs_client_secret=False,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
        note="Necesita una app OAuth propia en Google Cloud (una vez, puede ser la misma que ya uses para "
             "Google Drive) con la Photos Picker API habilitada."),
}


def get(provider_id: str) -> PhotosProvider | None:
    return PROVIDERS.get((provider_id or "").strip().lower())


def ids() -> list[str]:
    return list(PROVIDERS.keys())


def public_list() -> list[dict]:
    """Redacted list for the frontend connect form. No endpoints, no credentials."""
    out = []
    for p in PROVIDERS.values():
        out.append({
            "id": p.id, "label": p.label, "note": p.note, "default_tier": p.default_tier,
            "tiers": [{"id": t.id, "label": t.label, "browsable": t.browsable, "note": t.note}
                      for t in p.tiers],
        })
    return out
