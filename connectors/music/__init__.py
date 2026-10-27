"""connectors/music/ — SHARED music layer, provider-agnostic (V2-041).

Single facade used by FlashBrain (tool `play_music`) and — as a SEPARATE piece, later — the music widget. Routes the
intent ("play music", "play Frank Sinatra", "pause", "turn up the volume") to the CONNECTED provider (Spotify today;
the seam accepts any streaming connector). Never raises to the caller: returns a `MusicResult` with a speakable
sentence. Network I/O -> caller runs it with `asyncio.to_thread` (respects V2-011).
"""
from __future__ import annotations

import logging

from . import placement, registry
from .base import MusicProvider, MusicResult, NowPlaying, Track

logger = logging.getLogger("zaelar.music")

# Control actions WITHOUT data (all except 'play', which may carry query/uri).
_CONTROL = {"pause", "resume", "next", "previous", "stop"}
_VOLUME = {"volume_up", "volume_down", "set_volume"}

def _msg(key: str) -> str:
    """A seam line (no provider / a provider failure) in the active language — the words live in the `voice`
    pack (`music.<key>`), so a generated language says its own and never inherits Spanish."""
    from i18n import langs as _langs
    return _langs.words(f"music.{key}", default="")


def active_provider(prefer: str = "") -> "MusicProvider | None":
    return registry.active(prefer)


def available() -> "list[str]":
    """Names of providers connected right now."""
    return [p.name for p in registry.available()]


def sounding_provider() -> "MusicProvider | None":
    """The provider the last start went to (V2-812), while it is still connected — what pause, volume and next must
    reach. None when nothing was started (the caller falls back to the active one)."""
    name = placement.recorded().get("provider", "")
    return next((p for p in registry.available() if name and p.name == name), None)


def _for_control(prefer: str = "") -> "MusicProvider | None":
    return active_provider(prefer) if prefer else (sounding_provider() or active_provider())


def _in_page() -> "MusicProvider | None":
    return next((p for p in registry.available() if getattr(p, "plays_in_page", False)), None)


def _choose(prefer: str, screen: str) -> "tuple[MusicProvider | None, dict | None]":
    """WHERE a start goes (V2-812): the active provider, unless it plays on a device elsewhere and has none on the
    screen that asked — then the provider that plays in that screen's page. (provider, device) — device only for a
    provider that plays elsewhere and found one there. An unknown screen keeps the old choice."""
    prov = active_provider(prefer)
    kind = placement.screen_kind(screen)
    if prov is None or not getattr(prov, "plays_elsewhere", False) or not kind:
        return prov, None
    dev = prov.device_near(kind)
    if dev or prefer:
        return prov, dev
    return (_in_page() or prov), None


def _start(prov: "MusicProvider", dev: "dict | None", screen: str, query: str, run) -> MusicResult:
    """Run one start on `prov`, read it back when the sound is elsewhere, fall back to the asking screen's page
    when the device there is not sounding, and record where it went. `run(prov, device_id)` is the start itself."""
    dev_id = (dev or {}).get("id", "")
    res = run(prov, dev_id)
    if getattr(prov, "plays_elsewhere", False):
        res = prov.confirm(res, dev_id) if res.ok else res
        # Silent, or refused by the device (gone, not Premium…): the asking screen's page plays it. A song the
        # provider could not FIND stays its answer — the caller's resolution chain handles that.
        if not res.ok and res.reason != "no_track":
            alt = _in_page() if placement.screen_kind(screen) else None
            if alt is not None:
                logger.info(f"music: {prov.name} not sounding on {res.extra.get('device')!r}, playing in the page")
                try:
                    prov.pause()                 # a device that starts late must not sound under the page player
                except Exception as _e:  # noqa: BLE001
                    logger.debug("_start: degraded, carrying on without it: %s", _e)
                    pass
                prov, dev, res = alt, None, run(alt, "")
    if res.ok:
        before = sounding_provider()
        if before is not None and before.name != prov.name:
            try:
                before.pause()                   # one sound: the player it moved away from goes quiet
            except Exception as _e:  # noqa: BLE001
                logger.debug("_start: degraded, carrying on without it: %s", _e)
                pass
        placement.record(prov.name, device_id=(res.extra or {}).get("device_id", dev_id),
                         device=(res.extra or {}).get("device", (dev or {}).get("name", "")),
                         screen=screen, query=query)
    return res


def _already(prov: "MusicProvider", query: str) -> "MusicResult | None":
    """The same words asked again while that start is sounding: say so instead of sending it again (V2-812). The
    in-page provider keeps its own guard (V2-047 F5); this is the one for a device elsewhere, where a repeated play
    restarted the song on a device he could not hear."""
    rec = placement.recorded()
    if not (query and getattr(prov, "plays_elsewhere", False) and rec.get("provider") == prov.name
            and placement.norm(rec.get("query", "")) == placement.norm(query)):
        return None
    np = prov.now_playing()
    if np is None or not np.playing or (rec.get("device_id") and np.device_id != rec.get("device_id")):
        return None
    from i18n import langs as _langs
    label = np.track.label() if np.track is not None else query
    msg = _langs.words("music.spotify.already_on", default="").format(label=label, device=np.device or prov.name)
    return MusicResult(ok=True, provider=prov.name, action="play", track=np.track, message=msg,
                       extra={"noop": True, "device": np.device, "device_id": np.device_id, "sounding": True})


def control(action: str, query: str = "", uri: str = "", percent: int = 0, prefer: str = "",
            seconds: float = 0.0, relative: bool = False) -> MusicResult:
    """Execute ONE music action against the active provider. `action`: play|pause|resume|next|previous|stop|
    volume_up|volume_down|set_volume|seek. FlashBrain facade — fail-safe, never raises."""
    action = (action or "play").strip().lower()
    from nucleo import consequence as _consequence
    if not _consequence.passes("music", action=action, query=query[:120]):
        return MusicResult(ok=True, action=action, reason="dry")
    if action == "play" and (query or uri):
        return _play(query, uri, prefer)
    prov = _for_control(prefer)
    if prov is None:
        return MusicResult(ok=False, action=action, reason="no_provider", message=_msg("no_provider"))
    try:
        if action == "play":
            return _confirmed(prov, prov.play(query=query, uri=uri))
        if action == "pause":
            return prov.pause()
        if action in ("resume", "reanuda", "sigue"):
            return _confirmed(prov, prov.resume())
        if action == "next":
            return prov.next()
        if action in ("previous", "prev", "back"):
            return prov.previous()
        if action == "stop":                       # 'stop' = pause (stop music, not kill processes)
            return prov.pause()
        if action == "queue":                       # V2-047 F4: add to queue (one after another)
            return prov.enqueue(query=query, uri=uri)
        if action == "ended":                       # V2-047 F4: widget says it ended -> next from queue
            return prov.on_ended()
        if action == "volume_up":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(min(100, cur + 15))
        if action == "volume_down":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(max(0, cur - 15))
        if action == "set_volume":
            return prov.set_volume(max(0, min(100, int(percent or 0))))
        if action == "seek":                        # V2-717: to a position, or by a number of seconds
            return prov.seek(float(seconds or 0.0), bool(relative))
    except Exception as e:  # noqa: BLE001 — a provider failure never breaks voice
        logger.warning(f"music.control({action}) falló: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action=action, reason="error",
                           message=_msg("done"))
    return MusicResult(ok=False, provider=prov.name, action=action, reason="error", message=_msg("done"))


def _confirmed(prov: "MusicProvider", res: MusicResult) -> MusicResult:
    """A resume of a provider that plays elsewhere is read back too: «Sigo» over a device that stays silent is the
    same lie as «Suena»."""
    return prov.confirm(res) if getattr(prov, "plays_elsewhere", False) else res


def _play(query: str, uri: str, prefer: str = "") -> MusicResult:
    """A start by words or uri, placed on the screen that asked (V2-812). Fail-safe: never raises."""
    screen = placement.asking_screen()
    prov, dev = _choose(prefer, screen)
    if prov is None:
        return MusicResult(ok=False, action="play", reason="no_provider", message=_msg("no_provider"))
    try:
        same = _already(prov, query) if not uri else None
        if same is not None:
            return same

        def run(p, dev_id):
            return p.play(query=query, uri=uri, device=dev_id) if dev_id else p.play(query=query, uri=uri)
        return _start(prov, dev, screen, query, run)
    except Exception as e:  # noqa: BLE001 — a provider failure never breaks voice
        logger.warning(f"music.control(play) failed: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action="play", reason="error", message=_msg("done"))


def play_list(items: "list[tuple[str, str]]") -> MusicResult:
    """Several tracks as ONE sequence on the provider placed for the asking screen — [(query, uri), …], the first
    sounding now (V2-795, V2-812). Fail-safe like `control`: never raises."""
    screen = placement.asking_screen()
    prov, dev = _choose("", screen)
    if prov is None:
        return MusicResult(ok=False, action="play", reason="no_provider", message=_msg("no_provider"))
    items = [(str(q or ""), str(u or "")) for q, u in (items or [])]
    if not items:
        return MusicResult(ok=False, provider=prov.name, action="play", reason="no_track")
    if getattr(prov, "plays_lists_as_context", False):
        try:
            def run(p, dev_id):
                if not getattr(p, "plays_lists_as_context", False):
                    return _play_one_then_queue(p, items)
                return p.play_list(items, device=dev_id) if dev_id else p.play_list(items)
            return _start(prov, dev, screen, items[0][0], run)
        except Exception as e:  # noqa: BLE001 — a provider failure never breaks voice
            logger.warning(f"music.play_list failed: {e!r}")
            return MusicResult(ok=False, provider=prov.name, action="play", reason="error", message=_msg("done"))
    # A provider whose queue is its own: the first now, the rest queued (V2-047 F4) — through `control`, the
    # one seam every other playback road takes.
    res = control("play", query=items[0][0], uri=items[0][1])
    for q, u in items[1:]:
        control("queue", query=q, uri=u)
    return res


def _play_one_then_queue(prov: "MusicProvider", items: "list[tuple[str, str]]") -> MusicResult:
    """The page's road for a list a device elsewhere could not sound: the first now, the rest in its own queue."""
    res = prov.play(query=items[0][0], uri=items[0][1])
    if res.ok:
        for q, u in items[1:]:
            prov.enqueue(query=q, uri=u)
    return res


def _guarded(action: str, fn) -> MusicResult:
    """Run one provider call fail-safe — the same contract as `control`: a provider failure never raises. It goes to
    the provider that is SOUNDING (V2-812), the first connected one when nothing was started."""
    prov = _for_control()
    if prov is None:
        return MusicResult(ok=False, action=action, reason="no_provider", message=_msg("no_provider"))
    try:
        return fn(prov)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music.{action} failed: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action=action, reason="error", message=_msg("done"))


def set_mode(shuffle: "bool | None" = None, repeat: "str | None" = None) -> MusicResult:
    """Shuffle on/off and/or repeat off|one|all on the active provider (V2-795)."""
    def run(prov):
        res = None
        if shuffle is not None:
            res = prov.set_shuffle(bool(shuffle))
        if repeat is not None and (res is None or res.ok):
            res = prov.set_repeat(str(repeat))
        return res or MusicResult(ok=False, provider=prov.name, action="mode", reason="no_change")
    return _guarded("mode", run)


def queue_list() -> "tuple[str, list[Track] | None]":
    """(provider name, what plays next) — None as the list when the provider does not expose its queue."""
    prov = _for_control()
    if prov is None:
        return "", None
    try:
        return prov.name, prov.queue_items()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music.queue_list via {prov.name} failed: {e!r}")
        return prov.name, None


def queue_edit(op: str, index: int = -1, to: int = -1) -> MusicResult:
    """remove | move | clear on the active provider's queue (V2-795)."""
    return _guarded("queue_" + str(op or ""), lambda prov: prov.queue_edit(op, int(index), int(to)))


def play_context(uri: str, label: str = "") -> MusicResult:
    """A whole album/playlist by the provider's own uri; `unsupported` when it cannot (play it track by track).
    Placed like any start (V2-812): a provider with no device on the asking screen answers `unsupported` through the
    page player, and the caller plays it track by track there."""
    screen = placement.asking_screen()
    prov, dev = _choose("", screen)
    if prov is None:
        return MusicResult(ok=False, action="play", reason="no_provider", message=_msg("no_provider"))
    try:
        def run(p, dev_id):
            return p.play_context(uri, label, device=dev_id) if dev_id else p.play_context(uri, label)
        return _start(prov, dev, screen, label, run)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music.play_context failed: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action="play", reason="error", message=_msg("done"))


def resolve(query: str) -> "Track | None":
    """The playable track a «title — artist» names, WITHOUT playing it: the first connected provider that finds it,
    in the registry's priority order (a connected streaming account first, the free YouTube-audio last). None when
    no provider is connected or none finds it. Network I/O, fail-safe: never raises."""
    q = (query or "").strip()
    if not q:
        return None
    for prov in registry.available():
        try:
            hits = prov.search(q, limit=1)
        except Exception as e:  # noqa: BLE001 — one provider failing hands over to the next
            logger.warning(f"music.resolve via {prov.name} failed: {e!r}")
            continue
        if hits:
            return hits[0]
    return None


def now_playing(prefer: str = "") -> "NowPlaying | None":
    """What the SOUNDING provider reports (V2-812) — the card and the brain read the player that makes the sound."""
    prov = _for_control(prefer)
    if prov is None:
        return None
    try:
        return prov.now_playing()
    except Exception as _e:  # noqa: BLE001
        logger.debug("now_playing: degraded, carrying on without it: %s", _e)
        return None


def status() -> dict:
    """State of ALL known providers (for UI/wizard/diagnostics)."""
    out = {}
    for p in registry.providers():
        try:
            out[p.name] = p.status()
        except Exception:  # noqa: BLE001
            out[p.name] = {"provider": p.name, "connected": False}
    return {"providers": out, "available": available()}


__all__ = ["control", "play_list", "sounding_provider", "placement", "set_mode", "queue_list", "queue_edit", "play_context", "resolve", "now_playing",
           "status", "available", "active_provider",
           "MusicProvider", "MusicResult", "NowPlaying", "Track", "registry"]
