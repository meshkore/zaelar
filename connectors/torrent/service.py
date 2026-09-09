"""The provider-agnostic facade of the torrent add-on — the only thing widgets and the API import.

Fail-safe by contract: every entry returns `{"ok": ...}` and NEVER raises to a caller, because a widget action
or a status poll must degrade to words, not to a traceback.

`available()` answers TWO questions that both have to be yes (V2-638): the libtorrent wheel imported (DERIVED,
never a hand-set flag — V2-603's rule), and the operator has not switched the client off. The switch is the one
he asked for by name: this is the single connector that can saturate a line, so someone on a metered or shared
connection must be able to stop it consuming data outright. It ships ENABLED — there is no credential and no
account to set up, so defaulting it off would just make the feature invisible.

The client is a SYSTEM TOOL, not the property of one widget: it downloads into the agent's own filesystem
(`library/downloads/`, its sandbox) and `file_it()` moves a finished file onto its shelf, from where every
widget can reach it by path. `want` says which shelf the caller came for, so the same client serves the video
widget, the music widget and a document fetch.
"""
from __future__ import annotations

from . import search, session


def enabled() -> bool:
    """The operator's switch (`config/connectors.json`), default ON."""
    try:
        from config import connectors as _cfg
        return bool(_cfg.enabled("torrent"))
    except Exception:  # noqa: BLE001 — an unreadable config must not disable a working client silently
        return True


def available() -> bool:
    """Usable at all? The wheel imported AND the operator has it switched on."""
    return session.available() and enabled()


def unavailable_reason() -> str:
    if not enabled():
        return "el cliente de descargas está desactivado en la configuración"
    return session.import_error() or "el cliente de torrent no está disponible en esta instalación"


def search_and_play(query: str, *, want: str = "media", keep: bool = False) -> dict:
    """Find a magnet via the mesh and start downloading it. `{ok, id, title}` or `{ok: False, error}`."""
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    found = search.find_magnet(query)
    if not found.get("ok"):
        return {"ok": False, "error": found.get("reason") or "no encontré nada para eso"}
    added = session.add_magnet(found["magnet"], want=want, keep=keep)
    if not added.get("ok"):
        return {"ok": False, "error": added.get("error") or "no pude iniciar la descarga",
                "unplayable": added.get("unplayable") or ""}
    return {"ok": True, "id": added["id"], "title": found.get("title") or query, "agent": found.get("agent")}


def add_magnet(magnet: str, *, want: str = "media", keep: bool = False) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.add_magnet(magnet, want=want, keep=keep)


def status(rid: str) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.status(rid)


def stream_url(rid: str) -> str:
    """Where a player points WHILE it downloads — the piece-aware route, not the library one (the file on
    disk is still full of holes until it finishes)."""
    return f"/api/torrent/stream/{rid}" if rid else ""


def file_it(rid: str) -> dict:
    """Move a FINISHED download out of the sandbox and onto its shelf, so every widget can reach it.

    Filing is ours, never the client's: that is what keeps the client's own access confined to
    `library/downloads/` (the operator's isolation rule)."""
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    if not session.is_complete(rid):
        return {"ok": False, "error": "esa descarga todavía no ha terminado"}
    path = session.saved_path(rid)
    if not path:
        return {"ok": False, "error": "no encuentro el fichero de esa descarga"}
    from library import index
    return index.file_into_place(path)


def active() -> list:
    if not available():
        return []
    return session.list_active()


def remove(rid: str) -> dict:
    if not available():
        return {"ok": False, "error": unavailable_reason()}
    return session.remove(rid)
