"""The provider-agnostic facade of the torrent add-on — the only thing the widget and the API import.

Fail-safe by contract: every entry returns `{"ok": ...}` and NEVER raises to a caller, because a widget action
or a status poll must degrade to words, not to a traceback. `available()` is DERIVED (the wheel imported, V2-603
rule) — a hand-set switch is a second thing to get wrong, and this one would be got wrong once, silently, on the
one machine that shipped without libtorrent.

One combined verb the widget leans on: `search_and_play(query)` — ask the mesh for a magnet, add it, and hand
back the id and title so the caller can open the player and start polling `status`. Search and add are also
exposed apart for the API and the tests.
"""
from __future__ import annotations

from . import search, session


def available() -> bool:
    """Is the add-on usable at all? False only where the libtorrent wheel is absent — then the connector is
    HIDDEN, not shown-and-broken (the video-connector rule): the card declines instead of spinning forever."""
    return session.available()


def unavailable_reason() -> str:
    return session.import_error() or "el cliente de torrent no está disponible en esta instalación"


def search_and_play(query: str) -> dict:
    """Find a magnet via the mesh and start downloading it. `{ok, id, title}` or `{ok: False, error}`."""
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    found = search.find_magnet(query)
    if not found.get("ok"):
        return {"ok": False, "error": found.get("reason") or "no encontré nada para eso"}
    added = session.add_magnet(found["magnet"])
    if not added.get("ok"):
        return {"ok": False, "error": added.get("error") or "no pude iniciar la descarga"}
    return {"ok": True, "id": added["id"], "title": found.get("title") or query, "agent": found.get("agent")}


def add_magnet(magnet: str) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.add_magnet(magnet)


def status(rid: str) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.status(rid)


def active() -> list:
    if not available():
        return []
    return session.list_active()


def remove(rid: str) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.remove(rid)
