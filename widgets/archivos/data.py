"""A real file manager — the agent's OWN library first, the operator's cloud drives beside it (V2-658).

Born as a read-only cloud-drive browser (V2-557). The operator's redesign: **one widget for files**, shaped
like any file manager — folders you navigate with rename/copy/delete, a file you double-click to open — with
the agent's own storage (`library/`, V2-638: video/audio/documents/images/downloads) as the DEFAULT provider,
and each connected cloud service (Drive, OneDrive, …) reachable from an icon in the header, exactly the
platform-icon-row shape `mensajeria`/`youtube` already use. His framing, verbatim in spirit: the WIDGET carries
every function: a connector that cannot do something (rename, in Drive's case — no write API here yet) simply
does not offer it; that is the connector's limit, never this widget's.

## Two providers, one vocabulary

`open_folder`/`go_up`/`go_home`/`search_files`/`open_file`/`refresh` work the same whatever `db.provider` is —
only what a `folderId`/`fileId` MEANS differs: for `local` it is a shelf id (`shelf:video`) or a library-relative
path; for a cloud provider it is that provider's own id, unchanged from V2-557. `rename_file`/`copy_file`/
`delete_file` are LOCAL ONLY — writing into someone's Drive is a different, bigger decision (V2-557's own
closing note), so a cloud provider answers those with a plain refusal naming the limit, never a silent no-op.

## Why the library has no real nested folders

`library/index.py::listing(kind=...)` classifies every file by EXTENSION across the whole tree, not by which
physical folder it sits in — the five shelves are a classification, not a directory an operator can create
subfolders inside. So "navigating a folder" here is one level deep, by design, not a cut corner: a `cut`/`paste`
between shelves would silently misfile a video into "Documentos" while `listing(kind="video")` kept finding it
anyway (it reads the extension, not the folder), which is a worse file manager than none. `copy_file` (a plain
in-place duplicate) is the operation that stays honest under that model; a real move is not offered.

## Opening a file routes to the widget that can play it

A widget must never call another widget's package directly (`widgets/AGENTS.md`'s isolation rule). `nucleo/
library_router` is the sanctioned `nucleo/`-layer hand-off — the same shape `nucleo/torrent_router.py` and
`nucleo/docsheet.py` already use — so this file never reaches into the video/music widgets' own code. A
playable image or document opens
INLINE (this card's own lightweight preview, `preview` in the action's reply — building a second reader is
cheaper and safer than reaching into `imagenes`/`documento`'s own stores); a playable video/audio hands off and
raises the player card; anything else is refused with the reason and a download link (`library/formats.py`'s own
`refusal()` — the operator's pendrive escape hatch).

## Reaching `connectors`/`library` is the pre-existing exemption

`archivos` is on the hand-reviewed `_STDLIB_EXEMPT` list (`widgets/validator.py`) since V2-557 — a cloud token
refreshed in the credential store has no stdlib equivalent. The cloud import stays DEFERRED for the same reason
as before (module import must not pay for `httpx`); `library.*` is pure stdlib underneath and costs nothing to
import, but is still reached lazily from inside functions, matching the file's own established shape.
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
# The reverse of `_FMT_KIND` (defined below) — a file's `library/formats.py` kind ("document") back to its
# shelf key ("documents"), so a row can name WHERE it lives. Only meaningful across a flat listing (a search
# spans every shelf); a plain single-shelf folder already says its shelf in the breadcrumb.
_SHELF_OF_FMT = {"video": "video", "audio": "audio", "document": "documents", "image": "images"}


def _seed() -> dict:
    return {
        "provider": "local", "folder_id": "", "trail": [], "entries": [], "next": "",
        "query": "", "selected": None, "mode": "list",
        "error": "", "reason": "", "updated": 0, "connected": False, "providers": [], "providers_updated": 0,
    }


def _migrate(db: dict, from_v: int) -> dict:
    if from_v < 2:
        # v1 could only ever be a cloud drive (provider "" meant "nothing connected yet"). v2's default
        # provider is the agent's own library, so a bare/empty provider now means LOCAL, not "please connect
        # something" — force a fresh listing under the new shape rather than replaying a stale cloud one.
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
    _a_local_write, _a_nav, _a_save_document, _a_set_provider, _a_set_view, _a_sync_providers, _a_torrent)
from .local import _reveal_in_os, _same_machine  # noqa: E402,F401 — tests reach both here; `local` calls the first through this module

ACTIONS = {
    "sync_providers": _a_sync_providers,
    "refresh": _a_nav,
    "open_folder": _a_nav,
    "go_up": _a_nav,
    "go_home": _a_nav,
    "search_files": _a_nav,
    "clear_search": _a_nav,
    "open_file": _a_nav,
    "save_document": _a_save_document,
    "reveal_local_file": _a_local_write,
    "rename_file": _a_local_write,
    "copy_file": _a_local_write,
    "delete_file": _a_local_write,
    "set_view": _a_set_view,
    "set_provider": _a_set_provider,
    "show_section": _a_torrent,
    "torrent_search": _a_torrent,
    "torrent_download": _a_torrent,
    "torrent_open": _a_torrent,
    "torrent_save": _a_torrent,
    "torrent_remove": _a_torrent,
    "torrent_poll": _a_torrent,
}


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
