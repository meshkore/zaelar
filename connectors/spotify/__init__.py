"""connectors/spotify/ — conector de música Spotify (Web API + OAuth PKCE), V2-041.

Implementa el contrato agnóstico `connectors.music.base.MusicProvider`. El registro de música lo carga de forma
perezosa por el símbolo `provider` (una instancia única). Ver `connectors/music/` (seam) y
`.meshkore/roadmap/initiatives/V2-041-conectores-musica.md`.
"""
from __future__ import annotations

from .provider import SpotifyProvider

# instancia única que el registro de `connectors.music` recoge (registry._BUILTIN['spotify'] = 'connectors.spotify:provider')
provider = SpotifyProvider()

__all__ = ["provider", "SpotifyProvider"]
