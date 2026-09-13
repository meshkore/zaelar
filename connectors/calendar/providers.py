#
# providers.py — SINGLE calendar-account provider registry (V2-679). Same shape as `connectors/video/providers.py`
# (V2-597) and `connectors/photos/providers.py` (V2-564) on purpose: a Google Calendar account connector is the
# same KIND of problem (OAuth + a provider that only shows what it is allowed to), so it reuses the pattern.
#
# v1 ships ONE provider (Google) but the registry is a FAMILY by design — the icons for iCloud and CalDAV
# (Outlook/Fastmail/Nextcloud) already exist in `widgets/agenda/widget.js` (V2-540's `_CALENDARS`/`CAL_SVG`),
# shown but INERT until a second provider lands here. Adding one touches this file, one client module and the
# connectors registry — zero lines of the widget change (the facade rule).
#
# ONE tier only, and it is READ+WRITE. Unlike the video connector (whose write tier was deliberately parked
# until it shipped, V2-596 T2), the operator's own spec for this build IS voice-driven writes — "add a meeting
# by voice, see it in real Google Calendar within seconds" is the acceptance test — so a read-only tier here
# would be a connector that cannot do the one thing it was built for.
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
class CalendarProvider:
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
    #: OAuth client SHIPPED with the engine (mirrors video's `builtin_client_id`, V2-603). EMPTY until Zaelar
    #: registers its own Google OAuth client — see INI-032 for the sibling video alta. A client_id is not a
    #: secret for an installed app (PKCE protects the exchange), which is why this can ship in a public repo.
    builtin_client_id: str = ""

    def tier(self, tier_id: str = "") -> ScopeTier:
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
        id="full", label="Lectura y escritura (todos tus calendarios)",
        scopes=("https://www.googleapis.com/auth/calendar",),
        note="Lee tus calendarios y sus citas, y puede crear/mover/borrar citas cuando se lo pidas por voz. "
             "Es el permiso que Google llama «gestionar tus calendarios» — sensible, no restringido."),
)

PROVIDERS: dict[str, CalendarProvider] = {
    # id "google" (not "google-calendar"): `widgets/agenda/data.py::_CALENDARS` already keys its header-strip
    # placeholder on "google" — a mismatch here would leave a stale "no disponible" row standing NEXT TO the
    # real one instead of becoming it (measured trap, T2 class: a consumer reads a field its producer doesn't
    # send).
    "google": CalendarProvider(
        id="google", label="Google Calendar",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        api_base="https://www.googleapis.com/calendar/v3",
        tiers=_GOOGLE_TIERS, default_tier="full",
        needs_client_secret=False,
        # Without access_type=offline + prompt=consent Google returns NO refresh_token at all (measured on the
        # Drive connector, V2-557, paid again on video/photos) — the connection would silently die within the hour.
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
        builtin_client_id="",
        note="Conecta tu Google Calendar: tus citas pasan a vivir ahí y esta agenda se sincroniza con ellas."),
}


def get(provider_id: str) -> CalendarProvider | None:
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
