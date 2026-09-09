#
# youtube/account.py — the ACCOUNT layer's actions (V2-597), extracted from data.py on 2026-09-09 paying the
# newborn-god-file ratchet (V2-632 grew data.py past 900 LOC; V2-555's rule: extract, never raise). Same
# delegation shape as library.py: `apply(action, p, db)` answers its own actions and returns None for the
# rest, so data.py keeps owning the dispatch and the two cannot disagree. Verbatim moves — nothing changed
# behavior; `_drop_blocked` is injected by data.py at import time to avoid a circular import.
#
import time

from .. import store

WID = "youtube"

_drop_blocked = None      # set by data.py right after import (the one seam back into it)


def _svc():
    """The video-account connector, imported here and never at module top: module import is what the widget
    CATALOG pays on every prompt, and it must not pull in httpx or the credential store (the archivos rule,
    written in its own docstring). Returns None if the package cannot load — callers report that as words."""
    try:
        from connectors.video import service
        return service
    except Exception:
        return None


def _accounts_enabled() -> bool:
    """Cheap and fail-CLOSED: an unreadable connector means the account layer stays hidden, never half-offered."""
    svc = _svc()
    if svc is None:
        return False
    try:
        return bool(svc.available())
    except Exception:
        return False


#: The one sentence every account action declines with, so the three doors cannot drift apart.
_NOT_YET = ("conectar cuentas de vídeo todavía no está disponible en esta versión — no es que esté "
            "desconectada, es que la puerta aún no existe")


def _sync_platforms(db: dict) -> dict:
    """Refresh the cached platform rows from the connector (local file reads, no network). The cache is what
    view_data serves — the hot path never imports the connector."""
    svc = _svc()
    db["platforms_at"] = int(time.time())
    if svc is None:
        db["platforms"] = []
        return {"ok": False, "error": "conector de vídeo no disponible", "platforms": []}
    st = svc.status()
    rows = []
    for r in (st.get("providers") or []):
        rows.append({"id": str(r.get("id") or ""), "label": str(r.get("label") or ""),
                     "connected": bool(r.get("connected")),
                     "app_configured": bool(r.get("app_configured")),
                     "note": str(r.get("note") or "")})
    db["platforms"] = rows
    return {"ok": bool(st.get("ok")), "platforms": rows}


def apply(action: str, p: dict, db: dict) -> "dict | None":
    """The account layer's actions; None when `action` is not ours."""
    if action == "sync_platforms":
        # V2-597 (internal, fired by the card on mount when the cache is stale): refresh which video
        # platforms exist / are connected. Local file reads only — never the provider's network.
        r = _sync_platforms(db)
        store.save(WID, db)
        return r

    if action == "open_connectors":
        if not _accounts_enabled():
            return {"ok": False, "error": _NOT_YET, "message": _NOT_YET}
        # V2-597 — the VOICE door into a platform's connect screen (V2-520 shape: intent only, never a
        # credential). The card consumes `connect_focus` once per timestamp and opens that platform's
        # wizard — or its status screen if it is already connected.
        platform = str(p.get("platform") or "").strip().lower()
        _sync_platforms(db)
        known = {r.get("id") for r in db.get("platforms") or []}
        if platform not in known:
            platform = "youtube" if "youtube" in known else ""
        db["connect_focus"] = {"platform": platform, "ts": int(time.time() * 1000)}
        store.save(WID, db)
        row = next((r for r in db.get("platforms") or [] if r.get("id") == platform), {})
        return {"ok": True, "platform": platform, "connected": bool(row.get("connected")),
                "app_configured": bool(row.get("app_configured"))}

    if action == "connect_account":
        if not _accounts_enabled():
            return {"ok": False, "error": _NOT_YET, "message": _NOT_YET}
        # Starts the OAuth consent for a platform whose app is ALREADY registered (client_id typed once in
        # ⚙ → Conectores, never through a widget payload — V2-520). Returns the URL; the card opens the
        # window synchronously on the click and fills its location after.
        platform = str(p.get("platform") or "youtube").strip().lower()
        svc = _svc()
        if svc is None:
            return {"ok": False, "error": "conector de vídeo no disponible"}
        r = svc.connect_url(platform)
        if not r.get("ok"):
            return {"ok": False, "error": str(r.get("error") or "no pude empezar la conexión")[:200]}
        return {"ok": True, "url": r.get("url"), "platform": platform}

    if action == "disconnect_account":
        platform = str(p.get("platform") or "youtube").strip().lower()
        svc = _svc()
        if svc is None:
            return {"ok": False, "error": "conector de vídeo no disponible"}
        r = svc.disconnect(platform)
        _sync_platforms(db)
        # A disconnected account's suggestions are stale by definition — keeping them would show a band the
        # data no longer backs.
        db["suggested"], db["suggested_at"], db["suggested_channels"] = [], 0, 0
        store.save(WID, db)
        return {"ok": bool(r.get("ok")), "platform": platform,
                **({} if r.get("ok") else {"error": str(r.get("error") or "")[:200]})}

    if action == "suggest":
        if not _accounts_enabled():
            return {"ok": False, "error": _NOT_YET, "message": _NOT_YET}
        # V2-597 — fill/refresh the HOME suggestions band from the connected account's subscriptions.
        # Pulled ONLY when asked (no background, decision in V2-597); blocked channels are dropped at this
        # door like at every other NAME door, and the count travels so the ack can say it (V2-414).
        platform = str(p.get("platform") or "youtube").strip().lower()
        svc = _svc()
        if svc is None:
            return {"ok": False, "error": "conector de vídeo no disponible"}
        db["suggesting"] = True
        store.save(WID, db)                              # visible state while the network pull runs
        try:
            r = svc.suggestions(platform)
        finally:
            db["suggesting"] = False
        if not r.get("ok"):
            store.save(WID, db)                          # turn the state off even on failure
            return {"ok": False, "error": str(r.get("error") or "no pude traer sugerencias")[:200],
                    "message": str(r.get("error") or "No pude traer sugerencias.")[:200]}
        items, n_blocked = _drop_blocked(r.get("items") or [], db.get("blocked_channels"))
        db["suggested"] = items
        db["suggested_at"] = int(time.time())
        db["suggested_channels"] = int(r.get("channels") or 0)
        _sync_platforms(db)                              # a successful pull proves the connection is live
        store.save(WID, db)
        out = {"ok": True, "n": len(items), "channels": db["suggested_channels"], "platform": platform}
        if n_blocked:
            out["blocked_out"] = n_blocked
        if r.get("reason"):
            out["reason"] = str(r.get("reason"))[:200]
        return out
    return None
