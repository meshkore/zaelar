"""nucleo/torrent_router.py — hand a Descargas row to the widget that can play it.

The `torrent` widget (`widgets/torrent/`) is a MANAGER: it lists what is downloading and seeding and lets the
operator remove a download or save a finished file, but it never plays anything itself. Playing a video or a
finished audio file belongs to the surface built for it — `youtube` (V2-638's `play_torrent`, which can also
ADOPT an id already in Descargas) and `musica` (`play_local`, once the file is filed onto its shelf).

A widget's own `apply_action` must never reach into a sibling's store — "widgets are dumb and never talk to
each other" (widgets/AGENTS.md). This module is the orchestrator that DOES cross that line, the same layer
`nucleo/docsheet.py` already uses to open a widget bound to state that lives outside it (there: a worker's
errand; here: a download the operator clicked "▶" on). `widgets/torrent/data.py` calls this instead of
importing `widgets.youtube`/`widgets.musica` directly.
"""
from __future__ import annotations


def route_video(rid: str, title: str = "") -> dict:
    """Adopt a downloading-or-finished torrent into the video player and raise it on screen."""
    try:
        from widgets.youtube import data as _yt
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude abrir el reproductor de vídeo: {str(e)[:120]}"}
    r = _yt.apply_action("play_torrent", {"id": rid, "title": title})
    if r.get("ok"):
        _show("youtube")
        _pause("musica")                   # one speaker — best-effort, mirrors widgets/producers.py's rule
    return r


def route_audio(rid: str, title: str = "") -> dict:
    """File a FINISHED audio download onto its shelf, then hand it to the music player and raise it."""
    from connectors.torrent import service
    filed = service.file_it(rid)
    if not filed.get("ok"):
        return filed
    try:
        from widgets.musica import data as _mus
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude abrir el reproductor de música: {str(e)[:120]}"}
    r = _mus.apply_action("play_local", {"path": filed.get("rel") or ""})
    if r.get("ok"):
        _show("musica")
        _pause("youtube")
    return r


def _show(wid: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "show", extra={"id": wid, "src": "user"})
    except Exception:  # noqa: BLE001 — raising a real card open must never fail on a log line
        pass


def _pause(wid: str) -> None:
    """Best-effort: the other exclusive-audio widget yields, same spirit as `widgets/producers.py`'s channel
    exclusivity — skipped here because that path needs a running event loop this call may not have."""
    try:
        if wid == "youtube":
            from widgets.youtube import data as _yt
            _yt.apply_action("pause", {})
        elif wid == "musica":
            from widgets.musica import data as _mus
            _mus.apply_action("pause", {})
    except Exception:  # noqa: BLE001
        pass
