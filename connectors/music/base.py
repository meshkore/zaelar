"""connectors/music/base.py — provider-agnostic music CONTRACT (V2-041).

zaelar plays music by VOICE ("play music", "play Frank Sinatra"). The mechanism CANNOT be tied to one specific
provider: Spotify today, YouTube Music / Apple / radio stream tomorrow. This module defines the **SINGLE contract**
that any music connector implements (`MusicProvider`) and the data types it returns (`Track`, `NowPlaying`).
FlashBrain and — later, as a SEPARATE piece — the music widget ALWAYS speak to this contract through the facade
(`connectors.music`), never to a specific provider.

Invariant: "the music widget works with ANY connector that can stream". A provider enters the registry
(`registry.register`) by declaring that it satisfies this contract; the facade chooses the CONNECTED one.
All calls are SYNCHRONOUS (network I/O) -> the hot-path caller runs them with `asyncio.to_thread` (like
`web_search`), never in the event loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Track:
    """A track, normalized and provider-independent."""
    id: str = ""
    uri: str = ""                 # opaque id playable by the provider (e.g. 'spotify:track:...')
    title: str = ""
    artist: str = ""
    album: str = ""
    art: str = ""                 # cover-art URL (for the future widget)
    duration_ms: int = 0

    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else (self.title or self.uri)


@dataclass
class NowPlaying:
    """Current playback state (for the future widget and voice Q&A)."""
    playing: bool = False
    track: "Track | None" = None
    device: str = ""
    volume: "int | None" = None
    provider: str = ""


@dataclass
class MusicResult:
    """Uniform result of a playback action (consumed by the voice ack)."""
    ok: bool
    provider: str = ""
    action: str = ""
    track: "Track | None" = None
    reason: str = ""              # stable failure code: no_provider | not_connected | no_track | no_device | error
    message: str = ""             # ready SPEAKABLE sentence (operator language) — FlashBrain says it as-is
    extra: dict = field(default_factory=dict)


class MusicProvider(ABC):
    """Contract implemented by ANY connector capable of streaming music.

    `name` = stable id ('spotify', 'youtube'...). `connected()` = valid credentials/session exist to play NOW. A
    provider is only offered to the facade if `connected()` is True. Control methods return a `MusicResult` with a
    speakable sentence (`message`) — they never raise to the caller (fail-safe: voice never breaks on music failure).
    """

    name: str = "base"

    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> "list[Track]": ...

    @abstractmethod
    def play(self, query: str = "", uri: str = "") -> MusicResult:
        """Play: by natural-language `query` (search + play the first), by explicit `uri`, or — with neither — resume
        whatever was there."""

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

    # ── QUEUE (V2-047 F4): play several "one after another" without the operator intervening at each cut ───────
    # Generic to the contract but OPTIONAL: a provider with a native queue (Spotify) implements it against its API;
    # the browser fallback (YouTube) keeps it in its store and advances on the player's `ended` event. Base =
    # unsupported (fail-safe), so a provider that does not have it yet does not break voice.
    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Add a track to the QUEUE (does not interrupt current playback). Base: unsupported."""
        return MusicResult(ok=False, provider=self.name, action="queue", reason="unsupported")

    def on_ended(self) -> MusicResult:
        """The current track ENDED -> play the next one from the queue (if any). Base: unsupported (providers with
        native auto-advance, like Spotify, do not need it)."""
        return MusicResult(ok=False, provider=self.name, action="ended", reason="unsupported")

    def status(self) -> dict:
        """Redacted PUBLIC view for the UI (never secrets). Overridable; base = connection only."""
        return {"provider": self.name, "connected": bool(self.connected())}
