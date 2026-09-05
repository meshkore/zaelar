#
# providers.py — SINGLE video-account provider registry (V2-597). Same shape as
# `connectors/files/providers.py` (V2-557) and `connectors/photos/providers.py` (V2-564) on purpose: a
# YouTube ACCOUNT connector is the same KIND of problem (OAuth + a provider that only shows what it is
# allowed to), so it reuses the pattern instead of inventing a fourth one.
#
# v1 ships ONE provider (YouTube) but the registry is a FAMILY by design: the operator expects more video
# platforms later, selected per platform and never mixed — adding one touches this file, one client module
# and the connectors registry, and ZERO lines of the widget (the facade rule).
#
# Only the READ tier is offered in v1. A write/manage tier (subscribe/unsubscribe on the operator's real
# account) is parked as V2-596 T2 — offering a tier whose actions do not exist yet would be a promise the
# product cannot keep, so it is deliberately NOT declared here until it ships.
#
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeTier:
    id: str
    label: str
    scopes: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class VideoProvider:
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


_YOUTUBE_TIERS = (
    ScopeTier(
        id="readonly", label="Solo lectura (suscripciones y sugerencias)",
        scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        note="Lee tus suscripciones y sus vídeos recientes para la pantalla de inicio del reproductor. "
             "No puede tocar tu cuenta."),
)

PROVIDERS: dict[str, VideoProvider] = {
    "youtube": VideoProvider(
        id="youtube", label="YouTube",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        api_base="https://www.googleapis.com/youtube/v3",
        tiers=_YOUTUBE_TIERS, default_tier="readonly",
        needs_client_secret=False,
        # Without access_type=offline + prompt=consent Google returns NO refresh_token at all (measured on
        # the Drive connector, V2-557) — the connection would silently die within the hour.
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
        note="Necesita una app OAuth propia en Google Cloud (una vez; puede ser la misma que ya uses para "
             "Google Drive o Fotos) con la YouTube Data API v3 habilitada. Cuota gratuita de sobra: leer "
             "las suscripciones cuesta 1 unidad de 10.000 diarias."),
}


def get(provider_id: str) -> VideoProvider | None:
    return PROVIDERS.get((provider_id or "").strip().lower())


def ids() -> list[str]:
    return list(PROVIDERS.keys())


def public_list() -> list[dict]:
    """Redacted list for the frontend connect form. No endpoints, no credentials."""
    out = []
    for p in PROVIDERS.values():
        out.append({
            "id": p.id, "label": p.label, "note": p.note, "default_tier": p.default_tier,
            "tiers": [{"id": t.id, "label": t.label, "note": t.note} for t in p.tiers],
        })
    return out
