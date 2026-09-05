"""The route table, and one small function per route.

Each handler takes `(request, payload)` and returns the dict that becomes the JSON body. Raising `Refusal` is
how a route says no with a reason; anything else raising is a bug, and the HTTP layer turns it into a 500 whose
text the caller never sees.

EVERY NUMBER OFF THE WIRE IS COERCED, NEVER TRUSTED. `int(payload["limit"])` on `{"limit": "lots"}` raises
inside the handler, which the layer above turns into a 500 — an internal-error status for what is really a bad
argument, and a stack frame's worth of noise in the log every time an agent guesses a field name wrong. `_as_int`
clamps instead, so a nonsense value behaves like an absent one.
"""
from __future__ import annotations

from .. import VERSION, audit, config
from ..fs import listing, reading, searching
from ..fs import roots as folders
from ..fs.entries import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, MAX_READ_BYTES

# What the engine may ask for. A capability the engine believes in is a promise to the user, so nothing appears
# here until it is really there: offering a browser hand-off the daemon cannot perform makes the agent tell the
# user it will open a window and then not.
CAPABILITIES = ["files.list", "files.read", "files.search"]

AUDIT_DEFAULT_LIMIT = 200
AUDIT_MAX_LIMIT = 1_000


def _as_int(payload: dict, key: str, default: int, lo: int, hi: int) -> int:
    """A number from the wire, clamped into a range it cannot leave. Anything unreadable becomes the default."""
    raw = payload.get(key)
    if raw is None or isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(value, hi))


def _as_text(payload: dict, key: str) -> str:
    raw = payload.get(key)
    return raw if isinstance(raw, str) else ""


# ── the routes ────────────────────────────────────────────────────────────────────────────────────────────

def health(_request, _payload: dict) -> dict:
    """Deliberately says nothing about the user. It is the only route reachable without the token, so what it
    reveals is what an unauthenticated caller on this machine may learn: that a daemon is here, and what it can
    do."""
    cfg = config.load()
    return {
        "ok": True,
        "daemon": "zaelar",
        "version": VERSION,
        "configured": bool(cfg.get("configured")),
        "capabilities": list(CAPABILITIES),
    }


def permissions(_request, _payload: dict) -> dict:
    cfg = config.load()
    return {"ok": True, "roots": folders.roots(), "configured": bool(cfg.get("configured")),
            "candidates": folders.candidates()}


def grant(request, payload: dict) -> dict:
    path = _as_text(payload, "path")
    granted = folders.grant(path)
    audit.record("permissions.grant", caller=request._caller(), path=path, outcome="ok")
    return {"ok": True, "roots": granted}


def revoke(request, payload: dict) -> dict:
    path = _as_text(payload, "path")
    remaining = folders.revoke(path)
    audit.record("permissions.revoke", caller=request._caller(), path=path, outcome="ok")
    return {"ok": True, "roots": remaining}


def list_dir(request, payload: dict) -> dict:
    limit = _as_int(payload, "limit", LIST_DEFAULT_LIMIT, 1, LIST_MAX_LIMIT)
    out = listing.list_dir(_as_text(payload, "path") or None, limit=limit)
    audit.record("files.list", caller=request._caller(), path=out.get("path"), outcome="ok",
                 detail={"entries": len(out.get("entries") or [])})
    return out


def read_file(request, payload: dict) -> dict:
    cap = _as_int(payload, "max_bytes", MAX_READ_BYTES, 1, MAX_READ_BYTES)
    out = reading.read_file(_as_text(payload, "path"), max_bytes=cap)
    audit.record("files.read", caller=request._caller(), path=out.get("path"), outcome="ok",
                 detail={"bytes": len(out.get("text") or ""), "truncated": bool(out.get("truncated"))})
    return out


def search(request, payload: dict) -> dict:
    limit = _as_int(payload, "limit", 100, 1, searching.SEARCH_MAX_LIMIT)
    out = searching.search(_as_text(payload, "query"), raw_path=_as_text(payload, "path") or None,
                           content=bool(payload.get("content")), limit=limit)
    audit.record("files.search", caller=request._caller(), path=_as_text(payload, "path") or None, outcome="ok",
                 detail={"query": out.get("query"), "hits": len(out.get("hits") or []),
                         "stopped_early": out.get("stopped_early")})
    return out


def read_audit(_request, payload: dict) -> dict:
    """Reading the log is not itself logged: it is the one operation whose record would be pure noise, and a log
    that records reads of itself grows without anybody doing anything."""
    limit = _as_int(payload, "limit", AUDIT_DEFAULT_LIMIT, 1, AUDIT_MAX_LIMIT)
    return {"ok": True, "entries": audit.tail(limit)}


TABLE: dict[tuple[str, str], object] = {
    ("GET", "/health"): health,
    ("GET", "/permissions"): permissions,
    ("POST", "/permissions/grant"): grant,
    ("POST", "/permissions/revoke"): revoke,
    ("POST", "/files/list"): list_dir,
    ("POST", "/files/read"): read_file,
    ("POST", "/files/search"): search,
    ("POST", "/audit"): read_audit,
}
