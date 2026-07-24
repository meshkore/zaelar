"""connectors/music/base.py — CONTRATO agnóstico de proveedor de música (V2-041).

zaelar reproduce música por VOZ ("pon música", "ponme a Frank Sinatra"). El mecanismo NO puede atarse a un
proveedor concreto: hoy Spotify, mañana YouTube Music / Apple / un stream de radio. Este módulo define el
**contrato ÚNICO** que cualquier conector-de-música implementa (`MusicProvider`) y los tipos de dato que devuelve
(`Track`, `NowPlaying`). El FlashBrain y —más adelante, pieza SEPARADA— el widget de música hablan SIEMPRE con
este contrato a través de la fachada (`connectors.music`), nunca con un proveedor concreto.

Invariante: "el widget de música funciona con CUALQUIER conector que sepa hacer streaming". Un proveedor entra al
registro (`registry.register`) declarando que cumple este contrato; la fachada elige el que esté CONECTADO.
Todas las llamadas son SÍNCRONAS (I/O de red) → el llamante de la ruta caliente las corre con `asyncio.to_thread`
(igual que `web_search`), nunca en el event loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Track:
    """Una pista, normalizada e independiente del proveedor."""
    id: str = ""
    uri: str = ""                 # id opaco reproducible por el proveedor (p.ej. 'spotify:track:...')
    title: str = ""
    artist: str = ""
    album: str = ""
    art: str = ""                 # URL de la carátula (para el widget futuro)
    duration_ms: int = 0

    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else (self.title or self.uri)


@dataclass
class NowPlaying:
    """Estado de reproducción actual (para el widget futuro y el Q&A por voz)."""
    playing: bool = False
    track: "Track | None" = None
    device: str = ""
    volume: "int | None" = None
    provider: str = ""


@dataclass
class MusicResult:
    """Resultado uniforme de una acción de reproducción (lo consume el ack de voz)."""
    ok: bool
    provider: str = ""
    action: str = ""
    track: "Track | None" = None
    reason: str = ""              # código de fallo estable: no_provider | not_connected | no_track | no_device | error
    message: str = ""             # frase HABLABLE lista (idioma del operador) — la dice el FlashBrain tal cual
    extra: dict = field(default_factory=dict)


class MusicProvider(ABC):
    """Contrato que implementa CUALQUIER conector capaz de reproducir música por streaming.

    `name` = id estable ('spotify', 'youtube'…). `connected()` = hay credenciales/sesión válidas para reproducir
    AHORA. Un proveedor solo se ofrece a la fachada si `connected()` es True. Los métodos de control devuelven un
    `MusicResult` con una frase hablable (`message`) — nunca lanzan al llamante (fail-safe: la voz nunca se rompe
    por un fallo de música).
    """

    name: str = "base"

    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> "list[Track]": ...

    @abstractmethod
    def play(self, query: str = "", uri: str = "") -> MusicResult:
        """Reproduce: por `query` en lenguaje natural (busca + reproduce la 1ª), por `uri` explícito, o —sin
        ninguno— reanuda lo que hubiera."""

    @abstractmethod
    def pause(self) -> MusicResult: ...

    @abstractmethod
    def resume(self) -> MusicResult: ...

    @abstractmethod
    def next(self) -> MusicResult: ...

    @abstractmethod
    def previous(self) -> MusicResult: ...

    @abstractmethod
    def set_volume(self, percent: int) -> MusicResult: ...

    @abstractmethod
    def now_playing(self) -> "NowPlaying | None": ...

    # ── COLA (V2-047 F4): reproducir varias "una detrás de otra" sin que el operador avise en cada corte ──────
    # Genético del contrato pero OPCIONAL: un proveedor con cola nativa (Spotify) la implementa contra su API; el
    # fallback de navegador (YouTube) la lleva en su store y avanza con el evento `ended` del reproductor. Base =
    # no soportado (fail-safe), para que un proveedor que aún no la tenga no rompa la voz.
    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Añade una pista a la COLA (no interrumpe lo que suena). Base: no soportado."""
        return MusicResult(ok=False, provider=self.name, action="queue", reason="unsupported")

    def on_ended(self) -> MusicResult:
        """La pista actual TERMINÓ → reproduce la siguiente de la cola (si hay). Base: no soportado (los
        proveedores con auto-avance nativo, como Spotify, no lo necesitan)."""
        return MusicResult(ok=False, provider=self.name, action="ended", reason="unsupported")

    def status(self) -> dict:
        """Vista PÚBLICA redactada para la UI (nunca secretos). Sobrescribible; base = solo conexión."""
        return {"provider": self.name, "connected": bool(self.connected())}
