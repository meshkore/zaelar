"""Find a magnet for a query by asking the MeshKore network — never by scraping a site ourselves.

A torrent-search agent lives in the Oracle (it queries several indexers and returns an active magnet for
criteria). We go through `mesh_agents.serve` exactly like any other errand: free agents only, a 402 is a fact
and never paid, and «nobody does this» comes back as a speakable reason. This module's whole job is to pull the
magnet out of whatever shape the agent answers with — the contract is loose on purpose, because the agent is a
separate service that may phrase its payload as `magnet`, `magnet_uri`, a `link`, or a list of `results`.
"""
from __future__ import annotations

import html
import re

_MAGNET_RE = re.compile(r"magnet:\?[^\s\"'<>]+")

#: How many releases a catalogue keeps. The agent answers ~10; a screen of cards and a spoken «la tercera»
#: both stay readable at this size.
CATALOG_MAX = 12


def _clean_magnet(m: str) -> str:
    """The agent HTML-escapes its magnets (`&amp;dn=…&amp;tr=…`, measured 2026-09-24): as sent, the name and
    every tracker after the first `&` are parameters called `amp;dn` and `amp;tr`, which nothing reads."""
    return html.unescape(str(m or "")).strip()


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
    magnet = _clean_magnet(_first_magnet(res.get("data")))
    if not magnet:
        return {"ok": False, "reason": "el agente no devolvió ningún enlace magnet activo"}
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    title = str(data.get("title") or data.get("name") or query)[:160]
    return {"ok": True, "magnet": magnet, "title": title, "agent": res.get("agent")}


def _release(r: dict) -> dict | None:
    """One catalogue row, normalised to what a person reads and what a download needs — and nothing else.

    Dropped on purpose: `torrent_url`, which carries the agent's own indexer API key in its query string
    (measured 2026-09-24). It is not needed to download (the magnet is) and it must never reach a screen,
    a store or a prompt."""
    if not isinstance(r, dict):
        return None
    magnet = _clean_magnet(_first_magnet({"magnet": r.get("magnet")}))
    if not magnet:
        return None
    q = r.get("quality") if isinstance(r.get("quality"), dict) else {}
    res_ = str(q.get("resolution") or "").strip()
    return {
        "title": str(r.get("title") or "").strip()[:200] or "sin título",
        "magnet": magnet,
        "info_hash": str(r.get("info_hash") or "").lower()[:64],
        "size_bytes": int(r.get("size_bytes") or 0),
        "size": str(r.get("size_human") or "").strip()[:20],
        "seeders": int(r.get("seeders") or 0),
        "leechers": int(r.get("leechers") or 0),
        "resolution": "" if res_ in ("", "unknown") else res_[:12],
        "kind": str(r.get("kind") or "").strip()[:20],
        "published": str(r.get("published_at") or "")[:10],
    }


def find_releases(query: str) -> dict:
    """The CATALOGUE for a query: `{ok, releases:[…], agent}` best first, or `{ok: False, reason}`.

    Nothing is downloaded here — this is what a person looks at before choosing (V2-764). The order is the
    agent's own (`best` first, then `releases`), de-duplicated by info hash."""
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
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    raw = [data.get("best")] + list(data.get("releases") or [])
    out, seen = [], set()
    for r in raw:
        row = _release(r)
        if not row:
            continue
        key = row["info_hash"] or row["magnet"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= CATALOG_MAX:
            break
    if not out:
        # An agent that answers one bare magnet (the older contract) still makes a one-row catalogue.
        magnet = _clean_magnet(_first_magnet(res.get("data")))
        if not magnet:
            return {"ok": False, "reason": "el agente no devolvió ningún enlace magnet activo"}
        out = [{"title": str(data.get("title") or data.get("name") or query)[:200], "magnet": magnet,
                "info_hash": "", "size_bytes": 0, "size": "", "seeders": 0, "leechers": 0,
                "resolution": "", "kind": "", "published": ""}]
    return {"ok": True, "releases": out, "agent": res.get("agent")}
