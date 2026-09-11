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

WIDGET_ID = "archivos"
DB_VERSION = 2

# How long a cached listing is considered fresh enough to show without asking the provider again.
FRESH_S = 120
# What travels into the prompt when the card is open.
DIGEST_ENTRIES = 25
_MODES = ("list", "grid")

_SHELF_LABEL = {"video": "Vídeo", "audio": "Audio", "documents": "Documentos",
                "images": "Imágenes", "downloads": "Descargas"}
# The reverse of `_FMT_KIND` (defined below) — a file's `library/formats.py` kind ("document") back to its
# shelf key ("documents"), so a row can name WHERE it lives. Only meaningful across a flat listing (a search
# spans every shelf); a plain single-shelf folder already says its shelf in the breadcrumb.
_SHELF_OF_FMT = {"video": "video", "audio": "audio", "document": "documents", "image": "images"}


def _seed() -> dict:
    return {
        "provider": "local", "folder_id": "", "trail": [], "entries": [], "next": "",
        "query": "", "selected": None, "mode": "list", "panel": "",
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
        "panel": db.get("panel") or "",
        "error": db.get("error") or "",
        "reason": db.get("reason") or "",
        "count": len(db.get("entries") or []),
        "needs_refresh": bool(stale and not db.get("error")),
        "updated": int(db.get("updated") or 0),
    }


def ref_index() -> list[dict]:
    """The entries currently on screen, so `widgets/refs.py` can turn «the videos folder»/«that file» into a
    real id. `field` differs by kind: a folder is opened with `folderId`, a file targeted with `fileId` — one
    field shared by `open_file`/`rename_file`/`copy_file`/`delete_file`, all of which target the same rows."""
    out = []
    for e in (_load().get("entries") or [])[:400]:
        eid = str(e.get("id") or "")
        if not eid:
            continue
        is_folder = str(e.get("kind")) == "folder"
        hint = "carpeta" if is_folder else (str(e.get("file_kind") or "").strip()
                                            or str(e.get("mime") or "").split("/")[-1] or "archivo")
        out.append({"id": eid, "label": str(e.get("name") or ""),
                    "field": "folderId" if is_folder else "fileId", "hint": hint})
    return out


def _where(db: dict) -> str:
    return " / ".join([str(t.get("name") or "") for t in (db.get("trail") or [])]) or "raíz"


def prompt_digest() -> str:
    """What the brain sees while this card is OPEN (consumed by `widgets/brief.py` through `refs.prompt_digest`)."""
    db = _load()
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


# ── local library ──────────────────────────────────────────────────────────────────────────────────────────
# `library/paths.py::KINDS` names FOLDERS ("images", "documents" — plural, genesis-facing) while
# `library/formats.py::kind_of()` classifies a FILE ("image", "document" — singular). The two vocabularies
# never had to meet before this widget: every other caller only ever filtered by "video"/"audio", where
# singular and plural happen to coincide. Mapped here rather than in `library/` itself — changing a shared
# module's contract for one caller is a bigger, riskier edit than translating at the one seam that needs it.
_FMT_KIND = {"video": "video", "audio": "audio", "documents": "document", "images": "image"}


def _shelf_listing(kind: str) -> list[dict]:
    """Everything ON a shelf. `downloads` is the one shelf that is a PLACE, not a classification (the torrent
    sandbox, V2-638) — `library/index.py::listing()` only filters by extension-derived kind, so it cannot
    answer "what's physically in this folder"; that one is walked directly instead."""
    from library import index as _idx
    if kind == "downloads":
        return _downloads_listing()
    return _idx.listing(kind=_FMT_KIND.get(kind, kind))


def _downloads_listing() -> list[dict]:
    import os
    from library import index as _idx, paths as _paths
    d = _paths.downloads_dir()
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if n.startswith(".") or n.endswith(".part"):
            continue
        p = d / n
        if not p.is_file():
            continue
        rec = _idx.entry_for(_paths.rel_of(p))
        if rec:
            out.append(rec)
    return out


def _local_row(rec: dict) -> dict:
    modified = ""
    ts = int(rec.get("updated") or 0)
    if ts:
        try:
            from datetime import datetime, timezone
            modified = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            modified = ""
    return {"id": rec["rel"], "name": rec["name"], "kind": "file", "file_kind": rec["kind"],
            "mime": rec["mime"], "size": rec["size"], "modified": modified, "provider": "local",
            "playable": rec["playable"], "url": rec["url"], "download_url": rec["download_url"],
            "same_machine": _same_machine(), "shelf": _SHELF_OF_FMT.get(rec["kind"], "")}


def _shelf_rows() -> list[dict]:
    from library import paths as _paths
    rows = []
    for kind in _paths.KINDS:
        n = len(_shelf_listing(kind))
        rows.append({"id": f"shelf:{kind}", "name": _SHELF_LABEL.get(kind, kind), "kind": "folder",
                     "mime": "", "size": None, "modified": "", "provider": "local", "count": n})
    return rows


def _relist_local(db: dict, folder_id: str) -> dict:
    from library import paths as _paths
    db["query"] = ""
    db["error"] = ""
    db["reason"] = ""
    fid = str(folder_id or "").strip()
    if not fid:
        db["entries"] = _shelf_rows()
        db["trail"] = []
        db["folder_id"] = ""
        return db
    kind = fid.split(":", 1)[1] if fid.startswith("shelf:") else fid
    if kind not in _paths.KINDS:
        db["entries"] = []
        db["trail"] = []
        db["folder_id"] = ""
        db["error"] = f"no existe la carpeta «{fid}»"
        return db
    recs = _shelf_listing(kind)
    db["entries"] = [_local_row(r) for r in recs]
    db["trail"] = [{"id": f"shelf:{kind}", "name": _SHELF_LABEL.get(kind, kind)}]
    db["folder_id"] = f"shelf:{kind}"
    return db


def _local_search(q: str) -> list[dict]:
    from library import index as _idx
    ql = q.strip().lower()
    recs = _idx.listing()
    hits = [r for r in recs if ql in r["name"].lower()]
    return [_local_row(r) for r in hits[:200]]


def _open_local(rel: str) -> dict:
    from library import formats as _fmt, index as _idx
    rec = _idx.entry_for(rel)
    if not rec:
        return _err("no encuentro ese archivo en la biblioteca")
    fk = rec["kind"]
    if fk == "video":
        if not rec["playable"]:
            return _err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])
        from nucleo import library_router
        return library_router.route_video(rel, rec["name"])
    if fk == "audio":
        if not rec["playable"]:
            return _err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])
        from nucleo import library_router
        return library_router.route_audio(rel, rec["name"])
    if fk == "image" and rec["playable"]:
        return {"ok": True, "preview": {"kind": "image", "url": rec["url"], "name": rec["name"]}}
    if fk == "document" and rec["playable"]:
        return {"ok": True, "preview": {"kind": "document", "url": rec["url"], "name": rec["name"],
                                        "mime": rec["mime"]}}
    return _err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])


def _handle_local_nav(db: dict, act: str, payload: dict) -> dict:
    from library import paths as _paths

    if act == "open_file":
        fid = _text(payload.get("fileId") or payload.get("id"), 400)
        if not fid:
            return _err("dime QUÉ archivo abro")
        return _open_local(fid)

    if act == "search_files":
        q = _text(payload.get("query") or payload.get("q"), 200)
        if not q:
            return _err("dime qué busco dentro de tu biblioteca")
        matches = _local_search(q)
        db["query"] = q
        db["trail"] = []
        db["entries"] = matches
        db["selected"] = None
        db["error"] = ""
        db["reason"] = ""
        _save(db)
        return {"ok": True, "query": q, "count": len(matches), "matches": _matches(matches)}

    if act == "clear_search":
        target = db.get("folder_id") or ""
    elif act == "go_home":
        target = ""
    elif act == "open_folder":
        target = _text(payload.get("folderId") or payload.get("id"), 200)
        if not target:
            return _err("dime QUÉ carpeta abro: elige video, audio, documents, images o downloads")
        if target in _paths.KINDS:
            target = f"shelf:{target}"
    elif act == "go_up":
        target = ""                                       # one level deep by design — see the module docstring
    else:                                                  # refresh
        if db.get("query"):
            matches = _local_search(db["query"])
            db["entries"] = matches
            _save(db)
            return {"ok": True, "query": db["query"], "count": len(matches), "matches": _matches(matches)}
        target = db.get("folder_id") or ""

    db = _relist_local(db, target)
    db["selected"] = None
    _save(db)
    if db.get("error"):
        return _err(db["error"])
    return {"ok": True, "folder_id": db["folder_id"], "count": len(db["entries"]),
            "where": _where(db), "entries": _matches(db["entries"])}


def _same_machine() -> bool:
    """Is the browser reading this card on the SAME machine the engine runs on? Self-host: yes, always — the
    engine process already IS the operator's own computer, so opening a Finder/Explorer window on it shows
    the operator something real. A cloud Machine: no — there is no local disk of the operator's to reveal, and
    trying would open a window on a remote, usually headless, server nobody is looking at."""
    try:
        from nucleo.cloud_account import is_cloud_account
        return not is_cloud_account()
    except Exception:  # noqa: BLE001 — an unreadable signal must default to the SAFE answer: offer nothing
        return False


def _reveal_in_os(path) -> bool:
    """Best-effort: ask the OS to show this file in its native file manager. Never raises — a desktop-less
    self-host (a headless Linux box someone still chose to run natively) simply reports it could not."""
    import subprocess
    import sys
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False, timeout=3)
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", "/select,", str(path)], check=False, timeout=3)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False, timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def _handle_local_write(db: dict, act: str, payload: dict) -> dict:
    from library import index as _idx
    fid = _text(payload.get("fileId") or payload.get("id"), 400)
    if not fid:
        return _err("dime QUÉ archivo")
    if act == "reveal_local_file":
        # Read-only from the LIBRARY's point of view (never touches the file) — kept in the "write" gate
        # anyway because, like the others, it makes no sense for a cloud provider (V2-658: the operator
        # caught a real duplicate — double-clicking an unplayable local file downloaded a SECOND copy into
        # his Mac's own Downloads folder, when the file already sat on that same Mac's disk in Zaelar's own
        # library). Local + self-host: reveal it in place. Anything else: nothing to reveal.
        if not _same_machine():
            return _err("el agente está en la nube: aquí no hay una carpeta local que abrir — descarga el "
                        "archivo si lo quieres en este ordenador")
        from library import paths as _paths
        p = _paths.resolve(fid)
        if p is None or not p.is_file():
            return _err("no encuentro ese archivo en la biblioteca")
        opened = _reveal_in_os(p)
        return {"ok": True, "path": str(p), "opened": opened}
    if act == "rename_file":
        name = _text(payload.get("name") or payload.get("newName"), 200)
        if not name:
            return _err("dime el nombre nuevo")
        res = _idx.rename(fid, name)
    elif act == "copy_file":
        res = _idx.duplicate(fid)
    else:                                                  # delete_file
        res = _idx.delete(fid)
    if not res.get("ok"):
        return _err(res.get("error") or "no pude completar la operación")
    db = _relist_local(db, db.get("folder_id") or "")
    _save(db)
    out = {"ok": True, "count": len(db["entries"])}
    if "rel" in res:
        out["rel"] = res["rel"]
    return out


# ── cloud drives ───────────────────────────────────────────────────────────────────────────────────────────
def _sync_status(db: dict, svc) -> dict:
    """Fold connection state AND the provider catalog into ONE `providers` list — never touches `provider`
    itself, which only the operator's `set_provider` action (or a connector picked by voice) may change."""
    st = svc.status()
    live = {p.get("id"): p for p in (st.get("providers") or [])}
    merged = []
    for cat in (svc.providers_public() or []):
        row = dict(cat)
        row.update(live.get(cat.get("id"), {}) or {})
        merged.append(row)
    for pid, row in live.items():
        if not any(m.get("id") == pid for m in merged):
            merged.append(dict(row))
    db["providers"] = merged
    db["connected"] = bool(st.get("connected"))
    db["providers_updated"] = int(time.time())
    return db


def _relist_cloud(db: dict, svc, folder_id: str) -> dict:
    res = svc.list_folder(db.get("provider") or "", folder_id or "")
    db["query"] = ""
    db["error"] = "" if res.get("ok") else _text(res.get("error"), 300)
    db["reason"] = _text(res.get("reason"), 300)
    db["entries"] = res.get("entries") or []
    db["next"] = res.get("next") or ""
    db["folder_id"] = folder_id or ""
    if res.get("provider"):
        db["provider"] = res["provider"]
    crumb = svc.breadcrumb(folder_id or "", db.get("provider") or "")
    db["trail"] = crumb.get("trail") or []
    return db


def _handle_cloud_nav(db: dict, svc, act: str, payload: dict) -> dict:
    if act == "open_file":
        fid = _text(payload.get("fileId") or payload.get("id"), 200)
        if not fid:
            return _err("dime QUÉ archivo abro: pásame su fileId (o su nombre)")
        res = svc.item(fid, db.get("provider") or "")
        if not res.get("ok"):
            return _err(res.get("error") or "no pude abrir ese archivo")
        entry = res.get("entry") or {}
        db["selected"] = entry
        _save(db)
        return {"ok": True, "file": {k: entry.get(k) for k in
                                     ("id", "name", "kind", "mime", "size", "modified", "web_url")}}

    if act == "search_files":
        q = _text(payload.get("query") or payload.get("q"), 200)
        if not q:
            return _err("dime qué busco dentro de tus archivos")
        res = svc.search(q, db.get("provider") or "")
        db["query"] = q
        db["folder_id"] = db.get("folder_id") or ""
        db["trail"] = []
        db["entries"] = res.get("entries") or []
        db["next"] = ""
        db["selected"] = None
        db["error"] = "" if res.get("ok") else _text(res.get("error"), 300)
        db["reason"] = _text(res.get("reason"), 300)
        _save(db)
        if db["error"]:
            return _err(db["error"])
        return {"ok": True, "query": q, "count": len(db["entries"]),
                "reason": db.get("reason") or "", "matches": _matches(db["entries"])}

    if act == "clear_search":
        db = _relist_cloud(db, svc, db.get("folder_id") or "")
        _save(db)
        return {"ok": True, "count": len(db["entries"])}

    if act == "go_home":
        target = ""
    elif act == "open_folder":
        target = _text(payload.get("folderId") or payload.get("id"), 200)
        if not target:
            return _err("dime QUÉ carpeta abro: pásame su folderId (o su nombre, y lo resuelvo con lo "
                        "que hay en pantalla)")
    elif act == "go_up":
        trail = db.get("trail") or []
        target = str(trail[-2]["id"]) if len(trail) >= 2 else ""
    else:                                                  # refresh
        target = db.get("folder_id") or ""
        if db.get("query"):
            res = svc.search(db["query"], db.get("provider") or "")
            db["entries"] = res.get("entries") or []
            db["error"] = "" if res.get("ok") else _text(res.get("error"), 300)
            db["reason"] = _text(res.get("reason"), 300)
            _save(db)
            return {"ok": True, "query": db["query"], "count": len(db["entries"]),
                    "matches": _matches(db["entries"])}
    db = _relist_cloud(db, svc, target)
    db["selected"] = None
    _save(db)
    if db.get("error"):
        return _err(db["error"])
    return {"ok": True, "folder_id": db["folder_id"], "count": len(db["entries"]),
            "where": _where(db), "reason": db.get("reason") or "", "entries": _matches(db["entries"])}


# ── dispatch ───────────────────────────────────────────────────────────────────────────────────────────────
def apply_action(action: str, payload: dict | None = None):
    payload = payload or {}
    act = str(action or "").strip()
    db = _load()

    if act == "sync_providers":
        # Cheap, read-only-feeling refresh of the header's provider chips — the icon row must be able to show
        # "Drive"/"OneDrive" BEFORE the operator ever opens the connect wizard. Mirrors `youtube`'s own
        # `sync_platforms` (V2-597): the card asks once when stale, `view_data` never touches the network.
        svc = _svc()
        if svc is None:
            return {"ok": True, "providers": []}
        db = _sync_status(db, svc)
        _save(db)
        return {"ok": True, "providers": db["providers"]}

    if act == "open_connectors":
        svc = _svc()
        if svc is None:
            return _err("el conector de archivos no está disponible en esta instalación")
        db = _sync_status(db, svc)
        db["panel"] = "connect"
        want = _text(payload.get("provider"), 40).lower()
        _save(db)
        return {"ok": True, "panel": "connect", "provider": want, "providers": svc.providers_public()}

    if act == "connect_provider":
        want = _text(payload.get("provider"), 40).lower() or (db.get("provider") or "")
        if not want or want == "local":
            return _err("dime qué servicio conecto: gdrive u onedrive")
        try:
            from connectors.files import oauth as _oauth
        except Exception:
            return _err("el conector de archivos no está disponible en esta instalación")
        if not _oauth.configured(want):
            return _err(f"«{want}» todavía no tiene su aplicación registrada. Entra en Configuración → "
                        f"Conectores y pega ahí su client_id (una sola vez).", needs_app=True)
        res = _oauth.authorize_url(want, _text(payload.get("tier"), 40))
        if not res.get("ok"):
            return _err(res.get("error") or "no pude preparar la conexión")
        db["panel"] = "connect"
        _save(db)
        return {"ok": True, "provider": want, "url": res.get("url"), "tier": res.get("tier") or ""}

    if act == "disconnect_provider":
        want = _text(payload.get("provider"), 40).lower()
        if not want:
            return _err("dime qué servicio desconecto")
        try:
            from connectors.files import oauth as _oauth
        except Exception:
            return _err("el conector de archivos no está disponible en esta instalación")
        _oauth.forget(want)
        svc = _svc()
        if svc is not None:
            db = _sync_status(db, svc)
        if db.get("provider") == want:
            db["provider"] = "local"
            db = _relist_local(db, "")
        db["panel"] = "connect"
        _save(db)
        return {"ok": True, "provider": want}

    if act == "close_connectors":
        db["panel"] = ""
        _save(db)
        return {"ok": True, "panel": ""}

    if act == "set_view":
        mode = _text(payload.get("mode"), 12).lower()
        if mode not in _MODES:
            return _err(f"vista desconocida: «{mode}». Usa list o grid")
        db["mode"] = mode
        _save(db)
        return {"ok": True, "mode": mode}

    if act == "set_provider":
        want = _text(payload.get("provider"), 40).lower() or "local"
        if want == "local":
            db["provider"] = "local"
            db = _relist_local(db, "")
            _save(db)
            return {"ok": True, "provider": "local", "count": len(db["entries"])}
        svc = _svc()
        if svc is None:
            return _err("el conector de archivos no está disponible en esta instalación")
        db = _sync_status(db, svc)
        connected = [p["id"] for p in (db.get("providers") or []) if p.get("connected")]
        if want not in connected:
            return _err(f"«{want}» no está conectado. Conectados ahora mismo: "
                        f"{', '.join(connected) or 'ninguno'}")
        db["provider"] = want
        db = _relist_cloud(db, svc, "")
        _save(db)
        return {"ok": True, "provider": want, "count": len(db["entries"])}

    provider = db.get("provider") or "local"

    if act in ("rename_file", "copy_file", "delete_file", "reveal_local_file"):
        if provider != "local":
            return _err(f"«{provider}» no permite modificar archivos desde aquí — solo se puede navegar, "
                        f"buscar y abrir")
        return _handle_local_write(db, act, payload)

    if act == "save_document":
        # V2-661 — a TEXT becomes a file ON A SHELF, whatever the provider on screen: the library is the one
        # place a file the operator asks for can land (a worker wrote the Declaration into the browser
        # widget's data dir — the only path it knew — and then watched this card not show it).
        return _save_document(db, payload)

    if act in ("refresh", "go_home", "open_folder", "go_up", "search_files", "clear_search", "open_file"):
        if provider == "local":
            return _handle_local_nav(db, act, payload)
        svc = _svc()
        if svc is None:
            return _err("el conector de archivos no está disponible en esta instalación")
        db = _sync_status(db, svc)
        if not db.get("connected"):
            return _err("no hay ningún servicio de archivos conectado. Dime que quieras conectarlo y te "
                        "abro el asistente (o entra en Configuración → Conectores)", panel_hint="connect")
        return _handle_cloud_nav(db, svc, act, payload)

    return _err(f"acción desconocida: «{act}». Las que hay: refresh, open_folder, go_up, go_home, "
                f"search_files, clear_search, open_file, save_document, rename_file, copy_file, delete_file, "
                f"reveal_local_file, set_view, set_provider, open_connectors, close_connectors, "
                f"connect_provider, disconnect_provider")


def _save_document(db: dict, payload: dict) -> dict:
    """`save_document {name, text, folderId?}` → a real file in the library, and the card lands on its shelf
    showing it. The caller gets `where` (the shelf label) and `path` (the absolute path on this machine — what
    a self-hosted operator can go and open) beside the entry; refusing an empty text names the fields."""
    from library import index as _idx
    name = _text(payload.get("name") or payload.get("title") or payload.get("filename"), 160)
    text = str(payload.get("text") or payload.get("body") or payload.get("content") or "")
    if not text.strip():
        return _err("no llegó ningún texto que guardar: manda `text` (el contenido) y `name` (el nombre del fichero)")
    fid = _text(payload.get("folderId") or payload.get("folder") or payload.get("shelf"), 40).lower()
    kind = fid.split(":", 1)[1] if fid.startswith("shelf:") else fid
    from library import paths as _paths
    kind = kind if kind in _paths.KINDS else "documents"
    res = _idx.save_text(name, text, kind=kind)
    if not res.get("ok"):
        return _err(res.get("error") or "no pude guardar el fichero")
    db["provider"] = "local"
    db["query"] = ""
    db["panel"] = ""
    db = _relist_local(db, f"shelf:{kind}")
    rec = res.get("entry") or {}
    db["selected"] = _local_row(rec) if rec else None
    _save(db)
    return {"ok": True, "file": db["selected"], "where": _SHELF_LABEL.get(kind, kind), "folder_id": f"shelf:{kind}",
            "path": res.get("path") or "", "rel": res.get("rel") or ""}


def _matches(entries: list) -> list[dict]:
    """The compact shape that travels back to the brain: enough to name a result out loud."""
    out = []
    for e in (entries or [])[:DIGEST_ENTRIES]:
        out.append({"id": e.get("id"), "name": e.get("name"), "kind": e.get("kind"),
                    "mime": e.get("mime"), "size": e.get("size")})
    return out
