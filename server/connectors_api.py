"""`/api/connectors/*` — the single connector inventory and the Architect token (V2-083/V2-561; from
`server/config_api.py`, refactor2710-13 T-03). Mounted through `config_api.router`."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


# ── Connectors (V2-083) — single registry + control for those authenticated by dynamic TOKEN ────────────────
@router.get("/api/connectors")
async def get_connectors():
    """SINGLE connector inventory (messaging/music/infra) with status + REDACTED config — for the Connectors tab.
    Writes go through each family's endpoints (`/api/messaging/*`, `/api/spotify/*`, `/api/meshkore/*`) plus the
    architect endpoints below."""
    try:
        from connectors import registry
        return JSONResponse({"connectors": registry.descriptors()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"connectors": [], "error": str(e)[:160]})


@router.get("/api/connectors/catalog")
async def get_connector_catalog():
    """The NOT-live half of the connector directory (V2-561/V2-526): `planned`/`not-possible` entries for
    the ChatWall "Conectores" tab's wishlist. Cheap and static — reads a handful of JSON manifests, no
    network, no model. `/api/connectors` above stays the live half; the frontend merges the two by family."""
    try:
        from connectors import catalog
        return JSONResponse({"catalog": catalog.wishlist()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"catalog": [], "error": str(e)[:160]})


@router.post("/api/connectors/architect/connect")
async def architect_connect(payload: dict):
    """Set the Architect daemon TOKEN (and optional URL) in the DYNAMIC store (config/connectors.json), NOT in .env —
    configurable/revocable from the UI. The token is secret (redacted on read)."""
    from config import connectors as cfg
    tok = str((payload or {}).get("token") or "").strip()
    if not tok:
        return JSONResponse({"ok": False, "error": "empty token"}, status_code=400)
    patch = {"token": tok, "enabled": True}
    url = str((payload or {}).get("url") or "").strip()
    if url:
        patch["url"] = url
    from nucleo import cloud_account as _acct
    if _acct.is_cloud_account():
        # A hosted engine is not the person's computer: loopback here is the engine's own container, where no
        # daemon runs. It needs the daemon's public HTTPS address, and it is saved only once that daemon answers —
        # a token alone used to read «connected» while every call failed.
        from urllib.parse import urlparse
        from connectors.architect import client
        host = (urlparse(url).hostname or "").lower() if url else ""
        if not url.startswith("https://") or host in ("127.0.0.1", "localhost", "::1", ""):
            return JSONResponse({"ok": False, "error": "hosted_needs_public_url"}, status_code=400)
        previous = dict(cfg.get("architect") or {})
        cfg.set("architect", patch)
        try:
            await client.list_projects()
        except Exception as e:  # noqa: BLE001 — reported to the person, and the previous setting restored
            cfg.set("architect", {"token": previous.get("token", ""), "url": previous.get("url", ""),
                                  "enabled": bool(previous.get("enabled"))})
            return JSONResponse({"ok": False, "error": "daemon_unreachable", "detail": str(e)[:200]},
                                status_code=400)
        return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})
    cfg.set("architect", patch)
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})


@router.post("/api/connectors/architect/disconnect")
async def architect_disconnect():
    """REVOKE the Architect token (delete it from the store). Leaves the connector disconnected."""
    from config import connectors as cfg
    cfg.set("architect", {"token": "", "enabled": False})
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})
