"""scope_tiers.py — how a TIERED provider picks its scope tier, for every account connector's provider table.

Five provider tables (files, photos, video, calendar, contacts) declare their providers as frozen dataclasses
with `tiers` and `default_tier`, and each carried the same lookup. `oauth_base.spec` reads it through `p.tier`.
"""
from __future__ import annotations


class Tiered:
    """Mixin for a provider dataclass that declares `tiers: tuple[<tier>, ...]` and `default_tier: str`."""

    def tier(self, tier_id: str = ""):
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
