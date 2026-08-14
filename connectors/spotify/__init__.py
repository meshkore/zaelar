"""connectors/spotify/ — Spotify music connector (Web API + OAuth PKCE), V2-041.

Implements the agnostic `connectors.music.base.MusicProvider` contract. The music registry loads it lazily through
the `provider` symbol (a singleton instance). See `connectors/music/` (seam) and
`.meshkore/roadmap/initiatives/V2-041-conectores-musica.md`.
"""
from __future__ import annotations

from .provider import SpotifyProvider

# singleton instance collected by the `connectors.music` registry
provider = SpotifyProvider()

__all__ = ["provider", "SpotifyProvider"]
