"""A GENERIC cloud-file browser — the drive the operator already has, on the canvas (V2-557).

The operator asked for a connector to their files in the cloud «Google Drive or OneDrive… and obviously we
would need a viewer, a file-navigation widget as close as possible to the ones that exist», drivable with the
mouse AND by voice: «get me into this folder, find me a file that has this data, list me this and that».

## Why this widget is GENERIC and the provider is not its business

The provider lives entirely behind `connectors.files.service`, which hands back ONE normalized entry shape
({id, name, kind, mime, size, modified, web_url, provider}). Nothing in this file knows what Drive or Graph
call things, so a third provider is a client module over there and zero lines here. That was an explicit part
of the order — «the file navigation widget has to be generic in case people use other connectors in the
future» — and it is also what stops this from becoming `widgets/google-drive`, a piece that would have to be
written again for OneDrive and again for the next one.

## Where the network happens, and why it is not in `view_data`

`view_data` is called on EVERY render and again on every `store.save` that the SSE rail pushes, so a fetch in
there would be an HTTP round trip per repaint. It serves the CACHE and nothing else. Every network call lives
in `apply_action`, which runs once per operator intent — the same split `search`/`youtube` already use, except
those fetch on read because their read IS the query.

Reaching `connectors/` from a widget is normally forbidden — that is the isolation invariant every GENERATED
widget must obey — and this one is on the hand-reviewed allowlist in `widgets/validator.py::_STDLIB_EXEMPT`,
next to `musica`, for the same reason: somebody's cloud drive sits behind an OAuth token refreshed in the
credential store, and there is no stdlib equivalent of that. The exemption is a hardcoded id in the validator,
never a manifest field, so a generated widget cannot grant itself one.

The import is still DEFERRED, inside the functions that need it, and that is not about the check: it keeps
module import — and therefore the catalog, and therefore every prompt that lists widgets — free of `httpx` and
of the credential store. A REGISTERED CALLBACK would have avoided the import entirely and was rejected: it
fails by never being registered, and a file browser that silently shows an empty drive is exactly the «born
dead» failure this engine has paid for repeatedly.

## Foreground-only, decided rather than defaulted (V2-034 asks every widget this)

No `tick`. A drive changes on its own, but polling somebody's cloud storage burns API quota to answer a
question nobody asked, and there is no proactive fact here the operator would want spoken. Browsing is an
intent, so it happens when there is an intent.
"""
from __future__ import annotations

import time

from .. import store

WIDGET_ID = "archivos"
DB_VERSION = 1

# How long a cached listing is considered fresh enough to show without asking the provider again. Short,
# because a stale file list is a wrong answer, and cheap to renew.
FRESH_S = 120
# What travels into the prompt when the card is open. A folder can hold thousands of files; the brain needs
# enough to answer «what is in here» and to resolve «open the contract», not an inventory.
DIGEST_ENTRIES = 25
_MODES = ("list", "grid")


def _seed() -> dict:
    return {
        "provider": "", "folder_id": "", "trail": [], "entries": [], "next": "",
        "query": "", "selected": None, "mode": "list", "panel": "",
        "error": "", "reason": "", "updated": 0, "connected": False, "providers": [],
    }


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION)


def _save(db: dict) -> dict:
    db["updated"] = int(time.time())
    store.save(WIDGET_ID, db)
    return db


def _svc():
    """The connector, imported here and not at module top — see the module docstring. Returns None if the
    connector package cannot be loaded at all, which the callers report as a plain error instead of raising."""
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
    """The cached view. CHEAP by contract: no network, no credential store, no import of the connector.

    `needs_refresh` is what the card reads on mount to ask for a listing ONCE. It is computed here rather than
    stored so it cannot go stale in the file: a cache written before a restart is still a cache with an age."""
    db = _load()
    age = int(time.time()) - int(db.get("updated") or 0)
    stale = age > FRESH_S or not db.get("updated")
    return {
        "provider": db.get("provider") or "",
        "providers": db.get("providers") or [],
        "connected": bool(db.get("connected")),
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
    """The entries currently on screen, so `widgets/refs.py` can turn «the contracts folder» into a real id.
    The model NEVER guesses an id (V2-026) — without this, every action that takes one is undrivable by voice.
    `field` differs by kind on purpose: a folder is opened with `folderId`, a file with `fileId`, and handing
    the resolver one name for both would let «open the budget» enter a folder called like the file."""
    out = []
    for e in (_load().get("entries") or [])[:400]:
        eid = str(e.get("id") or "")
        if not eid:
            continue
        is_folder = str(e.get("kind")) == "folder"
        out.append({"id": eid, "label": str(e.get("name") or ""),
                    "field": "folderId" if is_folder else "fileId",
                    "hint": "carpeta" if is_folder else (str(e.get("mime") or "").split("/")[-1] or "archivo")})
    return out


def prompt_digest() -> str:
    """What the brain sees while this card is OPEN (consumed by `widgets/brief.py` through `refs.prompt_digest`).
    With the listing in the prompt, «what is in this folder?» is a question about text we already have instead
    of a round trip, and «open the contract» resolves against names the model has actually read."""
    db = _load()
    if not db.get("connected"):
        return "ARCHIVOS: sin ningún servicio de archivos conectado todavía."
    entries = db.get("entries") or []
    where = " / ".join([str(t.get("name") or "") for t in (db.get("trail") or [])]) or "raíz"
    head = f"ARCHIVOS ({db.get('provider') or '?'}) — en «{where}»"
    if db.get("query"):
        head = f"ARCHIVOS ({db.get('provider') or '?'}) — resultados de buscar «{db.get('query')}»"
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


# ── write / navigate ───────────────────────────────────────────────────────────────────────────────────────
def _sync_status(db: dict, svc) -> dict:
    """Fold connection state AND the provider catalog into ONE `providers` list.

    They arrive from two places on purpose — `oauth.status()` knows what is connected, `providers_public()`
    knows what each permission tier buys — and the connect wizard needs both in the same row. Merging here,
    rather than letting the card fetch the catalog itself, is what keeps `widget.js` free of network: the
    wizard renders from `view_data` like everything else on this canvas."""
    st = svc.status()
    live = {p.get("id"): p for p in (st.get("providers") or [])}
    merged = []
    for cat in (svc.providers_public() or []):
        row = dict(cat)
        row.update(live.get(cat.get("id"), {}) or {})
        merged.append(row)
    # A provider the catalog does not list but the token store does (a rename, a downgrade) is still shown —
    # dropping it would hide a live connection the operator can no longer revoke from here.
    for pid, row in live.items():
        if not any(m.get("id") == pid for m in merged):
            merged.append(dict(row))
    db["providers"] = merged
    db["connected"] = bool(st.get("connected"))
    if not db.get("provider"):
        db["provider"] = st.get("active") or ""
    return db


def _relist(db: dict, svc, folder_id: str) -> dict:
    """Fetch one folder and fold the result into the store. Search state is cleared here because a folder
    listing and a search result share one `entries` list, and leaving the old query on screen over new rows
    would label the listing as something it is not."""
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


def apply_action(action: str, payload: dict | None = None):
    """Every action here is DISPLAY-ONLY: it changes what the card shows, never anything in the operator's
    drive. That is why none carries `confirm` and why the navigation ones are marked `"view": true` in the
    manifest — a pure «open me the Drive» must actually list it, not just raise the card (V2-545)."""
    payload = payload or {}
    act = str(action or "").strip()
    svc = _svc()
    if svc is None:
        return _err("el conector de archivos no está disponible en esta instalación")
    db = _load()
    db = _sync_status(db, svc)

    if act == "open_connectors":
        # The connect wizard lives INSIDE the card (house rule: a widget's sub-flow stays in its own card).
        # It is also in ⚙ → Conectores; both read the same catalog, so they cannot drift.
        db["panel"] = "connect"
        want = _text(payload.get("provider"), 40).lower()
        _save(db)
        return {"ok": True, "panel": "connect", "provider": want,
                "providers": svc.providers_public()}

    if act == "connect_provider":
        # The consent round trip is started HERE and not from `widget.js`, which may not touch the network at
        # all (widget contract: self-contained, no fetch). The card asks its own backend and gets back a URL to
        # open — the widget never speaks to the provider.
        #
        # NO CREDENTIAL travels in this payload, deliberately. Registering the OAuth app (client_id/secret) is
        # the ⚙ → Conectores form's job; the boundary is V2-520's, already pinned by a test elsewhere: VOICE
        # CARRIES INTENT, NEVER A CREDENTIAL. Declaring a client_secret in a manifest payload would put one in
        # front of the model on every turn that lists this widget's actions.
        want = _text(payload.get("provider"), 40).lower() or (db.get("provider") or "")
        if not want:
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
        # `url` goes back so the CARD can open the consent window. It is a provider URL with no secret in it.
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
        db = _sync_status(db, svc)
        if db.get("provider") == want:
            db["provider"] = ""
            db["entries"] = []
            db["trail"] = []
            db["folder_id"] = ""
            db["selected"] = None
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
        want = _text(payload.get("provider"), 40).lower()
        connected = [p["id"] for p in (db.get("providers") or []) if p.get("connected")]
        if want and want not in connected:
            return _err(f"«{want}» no está conectado. Conectados ahora mismo: "
                        f"{', '.join(connected) or 'ninguno'}")
        db["provider"] = want
        db = _relist(db, svc, "")
        _save(db)
        return {"ok": True, "provider": want, "count": len(db["entries"])}

    if not db.get("connected"):
        return _err("no hay ningún servicio de archivos conectado. Dime que quieras conectarlo y te abro "
                    "el asistente (o entra en Configuración → Conectores)",
                    panel_hint="connect")

    if act in ("refresh", "go_home", "open_folder", "go_up"):
        if act == "go_home":
            target = ""
        elif act == "open_folder":
            target = _text(payload.get("folderId") or payload.get("id"), 200)
            if not target:
                return _err("dime QUÉ carpeta abro: pásame su folderId (o su nombre, y lo resuelvo con lo "
                            "que hay en pantalla)")
        elif act == "go_up":
            trail = db.get("trail") or []
            # The trail is root → … → current, so the parent is the second-to-last crumb; with one crumb the
            # parent IS the root, which is an empty id.
            target = str(trail[-2]["id"]) if len(trail) >= 2 else ""
        else:
            target = db.get("folder_id") or ""
            if db.get("query"):                      # refreshing a search re-runs the search, not the folder
                res = svc.search(db["query"], db.get("provider") or "")
                db["entries"] = res.get("entries") or []
                db["error"] = "" if res.get("ok") else _text(res.get("error"), 300)
                db["reason"] = _text(res.get("reason"), 300)
                _save(db)
                return {"ok": True, "query": db["query"], "count": len(db["entries"]),
                        "matches": _matches(db["entries"])}
        db = _relist(db, svc, target)
        db["selected"] = None
        _save(db)
        if db.get("error"):
            return _err(db["error"])
        return {"ok": True, "folder_id": db["folder_id"], "count": len(db["entries"]),
                "where": " / ".join([str(t.get("name") or "") for t in db["trail"]]) or "raíz",
                "reason": db.get("reason") or "", "entries": _matches(db["entries"])}

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
        # The matches TRAVEL BACK (V2-541): «find me the Axa contract» is a question, and a data-op that only
        # repaints leaves the turn with nothing to say but «there you go» over a card the operator may not be
        # looking at.
        return {"ok": True, "query": q, "count": len(db["entries"]),
                "reason": db.get("reason") or "", "matches": _matches(db["entries"])}

    if act == "clear_search":
        db = _relist(db, svc, db.get("folder_id") or "")
        _save(db)
        return {"ok": True, "count": len(db["entries"])}

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
        # `web_url` is handed back rather than opened: a widget never reaches outside itself, and whether this
        # becomes a document on the canvas or a page in the browser is the brain's call, not this card's.
        return {"ok": True, "file": {k: entry.get(k) for k in
                                     ("id", "name", "kind", "mime", "size", "modified", "web_url")}}

    return _err(f"acción desconocida: «{act}». Las que hay: refresh, open_folder, go_up, go_home, "
                f"search_files, clear_search, open_file, set_view, set_provider, open_connectors, "
                f"close_connectors, connect_provider, disconnect_provider")


def _matches(entries: list) -> list[dict]:
    """The compact shape that travels back to the brain: enough to name a result out loud, never the full
    entry (a listing of 200 files would be a prompt of its own)."""
    out = []
    for e in (entries or [])[:DIGEST_ENTRIES]:
        out.append({"id": e.get("id"), "name": e.get("name"), "kind": e.get("kind"),
                    "mime": e.get("mime"), "size": e.get("size")})
    return out
