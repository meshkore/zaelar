"""
observability/api.py — read-only HTTP surface (`/api/observability/*`) + SESSION lifecycle.

Two surfaces with DIFFERENT permissions, and the difference matters:

**OPEN** — used by this installation's own interface from the operator's browser, which in a remote deployment
is NOT loopback. It does not expose content:
  GET  /api/observability/identity          → which installation this is and which session is open
  GET  /api/observability/catalog           → the family/type map rendered by the viewer's filter
  POST /api/observability/session/start     → work-session lifecycle: only the frontend knows when the
  POST /api/observability/session/end         operator actually starts and stops the agent (tab, ⏻ button)

**PROTECTED** — returns CONTENT (operator utterances, prompts, search results, whatever a
worker brought back). Anyone who can read this can read the entire conversation, so it goes through `_allowed()`:
  GET  /api/observability/flows             → latest flows with their summary (duration, pieces, tokens, errors)
  GET  /api/observability/flow/{corr_id}    → one complete flow, in order
  GET  /api/observability/sessions          → latest work sessions
  GET  /api/observability/session/{sid}     → ONE session with its shape (to open and audit it)
  GET  /api/observability/events            → raw events with `since_id` cursor (follow a live session)
  GET  /api/observability/stats             → axis coverage

`session/end` intentionally accepts an empty body: `sendBeacon` triggers it when closing the tab, and it cannot
negotiate anything.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import flows as _flows
from . import identity as _identity

router = APIRouter()

# ── WHO CAN READ THE CONTENT ─────────────────────────────────────────────────────────────────────────────────
# These routes were created for the local viewer and were OPEN: in a home installation it makes no difference (the
# port is reachable only by the machine itself), but the same code runs in deployments where the port IS reachable —
# and there «open» means that anyone who finds the URL gets the conversations. The
# guarded-until-configured pattern, the same one used throughout the rest of the system:
#
#   · without `ZAELAR_OBS_TOKEN` → **loopback only**. A local installation works exactly as before.
#   · with `ZAELAR_OBS_TOKEN` → the `X-Observability-Token` header is required, regardless of where it comes from. This
#     allows an operations tool to query a remote instance WITHOUT exposing the content to the world.
#
# Fail-closed: if the origin cannot be determined (without `request.client`), access is denied.
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _allowed(request: Request) -> bool:
    token = (os.getenv("ZAELAR_OBS_TOKEN") or "").strip()
    if token:
        got = request.headers.get("x-observability-token") or ""
        return hmac.compare_digest(got, token)     # constant-time comparison: does not leak the valid prefix
    host = (getattr(request, "client", None).host if getattr(request, "client", None) else "") or ""
    return host in _LOOPBACK


_DENIED = JSONResponse(
    {"error": "forbidden",
     "detail": "la observabilidad con contenido es local; define ZAELAR_OBS_TOKEN y manda X-Observability-Token"},
    status_code=403,
)


@router.get("/api/observability/identity")
async def identity_state():
    return JSONResponse(_identity.session_info())


@router.get("/api/observability/catalog")
async def catalog():
    """The COMPLETE MAP of what can be filtered: every `kind` the system knows how to emit and which family it
    belongs to. The viewer renders it in FULL when expanding the filters, instead of discovering it as events arrive
    — this way the operator immediately sees what can be turned on and off, even what has not happened today.

    The source is `voice/observer.py::_CAT`, the SAME one that assigns each event's family: the frontend does not
    duplicate the map; it requests it. A test prevents a new kind from being left out
    (`tests/infrastructure/unit/core/test_observer_categories.py`)."""
    from voice import observer as _obs
    return JSONResponse({"kinds": dict(sorted(_obs._CAT.items()))})


@router.get("/api/observability/flows")
async def list_flows(request: Request, limit: int = 50, session_id: str = "", user_id: str = ""):
    if not _allowed(request):
        return _DENIED
    return JSONResponse({"flows": _flows.flows(limit=min(limit, 500), session_id=session_id, user_id=user_id)})


@router.get("/api/observability/flow/{corr_id}")
async def one_flow(request: Request, corr_id: str, limit: int = 500):
    if not _allowed(request):
        return _DENIED
    return JSONResponse({"corr_id": corr_id, "events": _flows.flow(corr_id, limit=min(limit, 2000))})


@router.get("/api/observability/sessions")
async def list_sessions(request: Request, limit: int = 30, user_id: str = ""):
    if not _allowed(request):
        return _DENIED
    # `current` makes it clear which one is ALIVE. Without it, readers have to guess by comparing timestamps
    # — and a live session and one that ended a minute ago look very much alike.
    # `session_id`, NOT `id`: it is the key returned by `identity.session_info()`. With the wrong key this
    # silently returned "" and NO session was marked as alive — the most costly possible failure in an audit view,
    # because it does not look like an error: it looks as though nobody is working.
    return JSONResponse({"sessions": _flows.sessions(limit=min(limit, 500), user_id=user_id),
                         "current": _identity.session_info().get("session_id") or ""})


@router.get("/api/observability/session/{session_id}")
async def one_session(request: Request, session_id: str):
    if not _allowed(request):
        return _DENIED
    info = _flows.session(session_id)
    if not info:
        return JSONResponse({"error": "unknown_session", "session_id": session_id}, status_code=404)
    info["live"] = (session_id == (_identity.session_info().get("session_id") or ""))
    # `flows` (a number, from the summary) and `flows_detail` (the list) are intentionally DISTINCT fields: putting the
    # list in `flows` overwrote the summary counter, and anyone reading `flows` would sometimes receive a number and
    # sometimes an array depending on the route. One name with two types is a trap for whoever consumes this.
    info["flows_detail"] = _flows.flows(limit=500, session_id=session_id)
    return JSONResponse(info)


@router.get("/api/observability/events")
async def raw_events(request: Request, session_id: str = "", corr_id: str = "",
                     since_id: int = 0, limit: int = 500):
    """Raw events with a cursor. This route serves TWO purposes at once: following a live session
    (calling with the last `id` seen) and archiving it in full (paginating from 0)."""
    if not _allowed(request):
        return _DENIED
    rows = _flows.events(session_id=session_id, corr_id=corr_id,
                         since_id=since_id, limit=min(limit, 2000))
    return JSONResponse({"events": rows, "last_id": (rows[-1]["id"] if rows else int(since_id)),
                         "more": len(rows) == min(limit, 2000)})


@router.get("/api/observability/stats")
async def stats(request: Request):
    if not _allowed(request):
        return _DENIED
    return JSONResponse(_flows.stats())


@router.post("/api/observability/session/start")
async def session_start(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    # `""` and not `None` when nothing opened: with the agent ⏻ off `begin_session` opens no session (see its
    # docstring), and the caller reads this field as "which session am I in" — an empty string says "none",
    # a `null` invites a reader to treat the key as missing.
    info = _identity.begin_session(str((body or {}).get("source") or "frontend"),
                                   force=bool((body or {}).get("force")))
    return JSONResponse({"session_id": info.get("id") or "", "user_id": _identity.user_id()})


@router.post("/api/observability/session/end")
async def session_end(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    info = _identity.end_session(str((body or {}).get("reason") or "frontend"))
    return JSONResponse({"ended": info.get("id")})
