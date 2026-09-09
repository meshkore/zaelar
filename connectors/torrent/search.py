"""Find a magnet for a query by asking the MeshKore network — never by scraping a site ourselves.

A torrent-search agent lives in the Oracle (it queries several indexers and returns an active magnet for
criteria). We go through `mesh_agents.serve` exactly like any other errand: free agents only, a 402 is a fact
and never paid, and «nobody does this» comes back as a speakable reason. This module's whole job is to pull the
magnet out of whatever shape the agent answers with — the contract is loose on purpose, because the agent is a
separate service that may phrase its payload as `magnet`, `magnet_uri`, a `link`, or a list of `results`.
"""
from __future__ import annotations

import re

_MAGNET_RE = re.compile(r"magnet:\?[^\s\"'<>]+")


def _first_magnet(obj) -> str:
    """Walk a JSON-ish payload for the first magnet URI, wherever the agent put it."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        m = _MAGNET_RE.search(obj)
        return m.group(0) if m else ""
    if isinstance(obj, dict):
        # Prefer the fields an agent is likeliest to name, then fall back to any value.
        for k in ("magnet", "magnet_uri", "magnetUri", "link", "uri", "url"):
            got = _first_magnet(obj.get(k))
            if got:
                return got
        for v in obj.values():
            got = _first_magnet(v)
            if got:
                return got
        return ""
    if isinstance(obj, (list, tuple)):
        for v in obj:
            got = _first_magnet(v)
            if got:
                return got
    return ""


def find_magnet(query: str) -> dict:
    """`{ok: True, magnet, title}` or `{ok: False, reason}` (reason is meant to be said out loud)."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "reason": "dime qué busco"}
    try:
        from nucleo import mesh_agents
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"no pude consultar la red: {str(e)[:120]}"}
    res = mesh_agents.serve(f"find a torrent of {query}", prompt=query)
    if not res.get("ok"):
        return {"ok": False, "reason": res.get("reason") or "no hay ningún agente de torrents en la red"}
    magnet = _first_magnet(res.get("data"))
    if not magnet:
        return {"ok": False, "reason": "el agente no devolvió ningún enlace magnet activo"}
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    title = str(data.get("title") or data.get("name") or query)[:160]
    return {"ok": True, "magnet": magnet, "title": title, "agent": res.get("agent")}
