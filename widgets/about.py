#
# An app's PAGE — the read model behind the apps window (V2-823).
#
# The apps window lists the catalogue and, for the app he selects, shows a small page: who owns it, when it was
# created, its licence, what it does and the connectors it can use. This module composes that page and nothing
# else; it is a PROJECTION of what already exists, never a second source:
#
#   name        → `registry.widget_identity` (the operator's-language name, V2-694)
#   origin      → `registry.origin_of` (shipped or his)
#   owner       → manifest `owner`
#   created     → manifest `created` (YYYY-MM-DD)
#   licence     → manifest `licence` (an id such as "SUL-1.0"; the screen translates it)
#   about       → the UI string `widgets.<id>.about` in his language, else the manifest `description`
#   connectors  → manifest `connector_families`, read against the LIVE inventory with the one reader
#                 (`connectors.registry.serves`), so the page and the card's own source strip cannot disagree
#   forked      → the date in `forked_from` (a shipped app he customised)
#
# THE RULE: a field the manifest does not declare is ABSENT from the page — not empty, not «unknown», not guessed.
# The screen renders only the keys it receives, so an invented value would have to be written here, and nothing
# here writes one.
#
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import registry, runtime

router = APIRouter()

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LICENCE = re.compile(r"^[A-Za-z0-9.+-]{1,40}$")


def _text(key: str, fallback: str) -> str:
    try:
        from i18n import runtime as _i18n
        return _i18n.text(key, fallback) or fallback
    except Exception:  # noqa: BLE001 — an unreadable bundle falls back to the manifest, never crashes the page
        return fallback


def _connectors(families) -> list[dict] | None:
    """The live connectors serving the declared families, or None when the manifest declares none."""
    if not isinstance(families, list):
        return None
    fams = [str(f).strip() for f in families if str(f or "").strip()]
    if not fams:
        return None
    try:
        from connectors import registry as _conn
        rows = _conn.descriptors()
        serves = _conn.serves
    except Exception:  # noqa: BLE001 — an inventory that cannot be read lists nothing, it does not invent
        return []
    out, seen = [], set()
    for d in rows:
        cid = str(d.get("id") or "")
        if not cid or cid in seen or not any(serves(d, f) for f in fams):
            continue
        seen.add(cid)
        out.append({"id": cid, "label": str(d.get("label") or cid), "connected": bool(d.get("connected"))})
    return out


def about(widget_id: str) -> dict | None:
    """The page of one catalogue app, or None when the id is not in the catalogue."""
    w = runtime.get(widget_id)
    if not w:
        return None
    ident = registry.widget_identity(w)
    wid = ident["id"]
    page: dict = {"id": wid, "name": ident["name"], "origin": ident["origin"]}

    owner = str(w.get("owner") or "").strip()
    if owner:
        page["owner"] = owner
    created = str(w.get("created") or "").strip()
    if _DATE.match(created):
        page["created"] = created
    licence = str(w.get("licence") or "").strip()
    if _LICENCE.match(licence):
        page["licence"] = licence
    native = str(w.get("description") or "").strip()
    text = _text(f"widgets.{wid}.about", native).strip()
    if text:
        page["about"] = text
    conns = _connectors(w.get("connector_families"))
    if conns is not None:
        page["connectors"] = conns
    fk = w.get("forked_from")
    if isinstance(fk, dict) and _DATE.match(str(fk.get("date") or "")):
        page["forked"] = str(fk["date"])
    return page


@router.get("/widgets/{wid}/about")
async def about_endpoint(wid: str):
    """The page over HTTP (mounted by `widgets/server_api.py`). Off the event loop: the connector inventory it reads
    asks each connector for its state. The id is reduced to [A-Za-z0-9_-] at this boundary, as every widget route does."""
    page = await asyncio.to_thread(about, "".join(c for c in str(wid or "") if c.isalnum() or c in "-_"))
    return JSONResponse(page or {"error": "unknown widget"}, status_code=200 if page else 404)
