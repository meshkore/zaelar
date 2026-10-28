"""A real file manager — the agent's OWN library first, the operator's cloud drives beside it (V2-658).

The agent's storage (`library/`, V2-638: video/audio/documents/images/downloads) is the DEFAULT provider; each
connected cloud service (Drive, OneDrive, …) is reachable from an icon in the header. The WIDGET carries every
function: a connector that cannot do something simply does not offer it.

## Two providers, one vocabulary

`open_folder`/`go_up`/`go_home`/`search_files`/`open_file`/`refresh` work the same whatever `db.provider` is; only
what a `folderId`/`fileId` MEANS differs (a shelf id or library-relative path for `local`, the provider's own id for
a cloud one). `rename_file`/`copy_file`/`delete_file` are LOCAL ONLY: a cloud provider refuses them by name, never
with a silent no-op — writing into someone's Drive is a separate decision (V2-557).

## The library has no real nested folders

`library/index.py::listing(kind=...)` classifies files by EXTENSION, so the shelves are a classification, not
directories: navigation is one level deep by design. A move between shelves would misfile silently, so only
`copy_file` (an in-place duplicate) is offered.

## Opening a file routes to the widget that can play it

A widget never imports another widget's package: `nucleo/library_router` is the hand-off. Images and documents open
INLINE (`preview` in the reply); playable video/audio hands off and raises the player card; anything else is
refused with `library/formats.py::refusal()` and a download link.

## Reaching `connectors`/`library`

`archivos` is on the validator's `_STDLIB_EXEMPT` list (a cloud token refresh has no stdlib equivalent). The cloud
import stays DEFERRED (module import must not pay for `httpx`); `library.*` is also reached lazily.
"""
from __future__ import annotations

import time

from .. import store
from i18n import langs as _langs   # V2-778 F3-30: hints are read back aloud, in the agent's language
from . import torrents as _tor

WIDGET_ID = "archivos"
DB_VERSION = 2

# How long a cached listing is considered fresh enough to show without asking the provider again.
FRESH_S = 120
# What travels into the prompt when the card is open.
DIGEST_ENTRIES = 25
_MODES = ("list", "grid")
_LIBRARY_VERBS = ("refresh", "open_folder", "go_up", "go_home", "search_files", "clear_search", "open_file",
                  "reveal_local_file", "rename_file", "copy_file", "delete_file", "set_provider")

_SHELF_LABEL = {"video": "Vídeo", "audio": "Audio", "documents": "Documentos",
                "images": "Imágenes", "downloads": "Descargas"}
# The reverse of `local._FMT_KIND` — a file's kind ("document") back to its shelf key ("documents"), so a row in a
# flat listing (a search spans every shelf) can name WHERE it lives.
_SHELF_OF_FMT = {"video": "video", "audio": "audio", "document": "documents", "image": "images"}


def _seed() -> dict:
    return {
        "provider": "local", "folder_id": "", "trail": [], "entries": [], "next": "",
        "query": "", "selected": None, "mode": "list",
        "error": "", "reason": "", "updated": 0, "connected": False, "providers": [], "providers_updated": 0,
    }


def _migrate(db: dict, from_v: int) -> dict:
    if from_v < 2:
        # v2's default provider is the agent's library: an empty provider means LOCAL, and the stale v1 cloud
        # listing is dropped for a fresh one.
        db["provider"] = db.get("provider") or "local"
        db["folder_id"] = ""
        db["trail"] = []
        db["entries"] = []
        db["query"] = ""
        db["selected"] = None
        db["updated"] = 0
    return db


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _save(db: dict) -> dict:
    db["updated"] = int(time.time())
    store.save(WIDGET_ID, db)
    return db


def _svc():
    """The cloud connector, imported here and not at module top — see the module docstring."""
    try:
        from connectors.files import service
        return service
    except Exception:
        return None


def _text(raw, cap: int = 200) -> str:
    return " ".join(str(raw or "").split())[:cap]


def _err(msg: str, **extra) -> dict:
    out = {"ok": False, "error": _text(msg, 300)}
    out.update(extra)
    return out


# ── read ───────────────────────────────────────────────────────────────────────────────────────────────────
def view_data(q: str = ""):
    """The cached view. CHEAP by contract: no network, no credential store, no filesystem walk.

    `needs_refresh` is what the card reads on mount to ask for a listing ONCE. Local is USABLE with nothing
    connected — `connected` reads True the instant the provider is `local`, never gated on OAuth."""
    db = _load()
    age = int(time.time()) - int(db.get("updated") or 0)
    stale = age > FRESH_S or not db.get("updated")
    provider = db.get("provider") or "local"
    prov_age = int(time.time()) - int(db.get("providers_updated") or 0)
    return {
        "provider": provider,
        "providers": db.get("providers") or [],
        "providers_stale": bool(prov_age > FRESH_S or not db.get("providers_updated")),
        "connected": True if provider == "local" else bool(db.get("connected")),
        "folder_id": db.get("folder_id") or "",
        "trail": db.get("trail") or [],
        "entries": db.get("entries") or [],
        "next": db.get("next") or "",
        "query": db.get("query") or "",
        "selected": db.get("selected"),
        "mode": db.get("mode") if db.get("mode") in _MODES else "list",
        "error": db.get("error") or "",
        "reason": db.get("reason") or "",
        "count": len(db.get("entries") or []),
        "needs_refresh": bool(stale and not db.get("error")),
        "updated": int(db.get("updated") or 0),
        # V2-764 — the two sections of the file manager: his library, and the torrents on their way to it.
        "section": db.get("section") if db.get("section") in _tor.SECTIONS else "biblioteca",
        "torrents": _tor.view(db),
    }


def ref_index() -> list[dict]:
    """The entries currently on screen, so `widgets/refs.py` can turn «the videos folder»/«that file» into a
    real id. `field` differs by kind: a folder is opened with `folderId`, a file targeted with `fileId` — one
    field shared by `open_file`/`rename_file`/`copy_file`/`delete_file`, all of which target the same rows."""
    db = _load()
    out = _tor.refs(db)          # V2-764: catalogue rows (`item`) and live downloads (`id`) — their own fields
    for e in (db.get("entries") or [])[:400]:
        eid = str(e.get("id") or "")
        if not eid:
            continue
        is_folder = str(e.get("kind")) == "folder"
        hint = _langs.words("hints.folder", default="") if is_folder else (str(e.get("file_kind") or "").strip()
                                            or str(e.get("mime") or "").split("/")[-1] or _langs.words("hints.file", default=""))
        out.append({"id": eid, "label": str(e.get("name") or ""),
                    "field": "folderId" if is_folder else "fileId", "hint": hint})
    return out


def _where(db: dict) -> str:
    return " / ".join([str(t.get("name") or "") for t in (db.get("trail") or [])]) or "raíz"


def prompt_digest() -> str:
    """What the brain sees while this card is OPEN (consumed by `widgets/brief.py` through `refs.prompt_digest`)."""
    db = _load()
    if db.get("section") == "torrents":
        return _tor.digest(db)
    provider = db.get("provider") or "local"
    label = "tu biblioteca" if provider == "local" else f"({provider})"
    entries = db.get("entries") or []
    head = f"ARCHIVOS {label} — en «{_where(db)}»"
    if db.get("query"):
        head = f"ARCHIVOS {label} — resultados de buscar «{db.get('query')}»"
    if db.get("reason"):
        return f"{head}: {_text(db.get('reason'), 240)}"
    if not entries:
        return f"{head}: VACÍA."
    rows = []
    for e in entries[:DIGEST_ENTRIES]:
        mark = "📁" if str(e.get("kind")) == "folder" else "·"
        rows.append(f"{mark} {_text(e.get('name'), 80)}")
    more = len(entries) - len(rows)
    tail = f" (y {more} más)" if more > 0 else ""
    return f"{head}: " + " | ".join(rows) + tail


# ── dispatch ───────────────────────────────────────────────────────────────────────────────────────────────
from .actions import (  # noqa: E402 — the handlers read the helpers above back through this module
    _local_write, _nav, _a_save_document, _a_set_provider, _a_set_view, _a_sync_providers, _torrent)
from .local import _reveal_in_os, _same_machine  # noqa: E402,F401 — tests reach both here; `local` calls the first through this module

# One `_a_<action>` name per declared action (a shared handler is bound under each of its names); the table is
# read off those names, so no list of action words is written twice.
_a_refresh = _a_open_folder = _a_go_up = _a_go_home = _a_search_files = _a_clear_search = _a_open_file = _nav
_a_reveal_local_file = _a_rename_file = _a_copy_file = _a_delete_file = _local_write
_a_show_section = _a_torrent_search = _a_torrent_download = _a_torrent_open = _a_torrent_save = _torrent
_a_torrent_remove = _a_torrent_poll = _torrent
ACTIONS = {name[3:]: fn for name, fn in list(globals().items()) if name.startswith("_a_")}


def apply_action(action: str, payload: dict | None = None):
    payload = payload or {}
    act = str(action or "").strip()
    handler = ACTIONS.get(act)
    if handler is None:
        return _unknown(act)
    return handler(act, payload)


def _unknown(act: str) -> dict:
    return _err(f"acción desconocida: «{act}». Las que hay: refresh, open_folder, go_up, go_home, "
                f"search_files, clear_search, open_file, save_document, rename_file, copy_file, delete_file, "
                f"reveal_local_file, set_view, set_provider")


def _matches(entries: list) -> list[dict]:
    """The compact shape that travels back to the brain: enough to name a result out loud."""
    out = []
    for e in (entries or [])[:DIGEST_ENTRIES]:
        out.append({"id": e.get("id"), "name": e.get("name"), "kind": e.get("kind"),
                    "mime": e.get("mime"), "size": e.get("size")})
    return out
