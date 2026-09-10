"""nucleo/library_router.py — hand a library row to the widget that can play it (V2-658).

Sibling of `nucleo/torrent_router.py`, same reason to exist: `widgets/archivos/data.py` manages the agent's
own file library and must never import `widgets.youtube`/`widgets.musica` directly (`widgets/AGENTS.md`'s
isolation rule — widgets are dumb and never talk to each other). This module is the sanctioned `nucleo/`-layer
orchestrator that DOES hold both ends, exactly the pattern `nucleo/docsheet.py` already uses.
"""
from __future__ import annotations


def route_video(rel: str, title: str = "") -> dict:
    """Play a library video file in the video widget and raise it on screen."""
    try:
        from widgets.youtube import data as _yt
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude abrir el reproductor de vídeo: {str(e)[:120]}"}
    r = _yt.apply_action("play_local", {"path": rel, "title": title})
    if r.get("ok"):
        _show("youtube")
        _pause("musica")
    return r


def route_audio(rel: str, title: str = "") -> dict:
    """Play a library audio file in the music widget and raise it on screen."""
    try:
        from widgets.musica import data as _mus
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude abrir el reproductor de música: {str(e)[:120]}"}
    r = _mus.apply_action("play_local", {"path": rel, "title": title})
    if r.get("ok"):
        _show("musica")
        _pause("youtube")
    return r


def _show(wid: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "show", extra={"id": wid, "src": "user"})
    except Exception:  # noqa: BLE001
        pass


def _pause(wid: str) -> None:
    try:
        if wid == "youtube":
            from widgets.youtube import data as _yt
            _yt.apply_action("pause", {})
        elif wid == "musica":
            from widgets.musica import data as _mus
            _mus.apply_action("pause", {})
    except Exception:  # noqa: BLE001
        pass
