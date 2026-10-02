"""server/api_guard.py — who may call `/api/*` (V2-778 F4-35, 2026-10-02).

## Why

A self-hosted engine listens on the operator's own machine, and every one of its ~87 mutating routes trusted
whoever reached it. «Whoever reached it» includes any web page the operator has open: a page on another site
can `POST http://127.0.0.1:43917/api/lists` with a body the browser sends without asking anyone (a «simple»
request needs no preflight) and mint an order with the operator's authority; a page that rebinds its own DNS
name to 127.0.0.1 can also READ the answers. Only the MeshKore control plane had a guard
(`connectors/meshkore/server_api._guard`). The audit's measured cases: `/api/lists`, `/api/torrent/add`.

## The rule (the operator's choices, 2026-10-02)

Self-hosted (a process that is not part of account routing):
  · every `/api/*` request must name this engine in `Host` — localhost, 127.0.0.1, ::1 or local.zaelar.com
    (its DNS pins to 127.0.0.1 by design). A DNS-rebound page names the attacker's domain there;
  · every `/api/*` request must come from the machine itself (a loopback peer);
  · a MUTATING request (POST/PUT/PATCH/DELETE) that a browser sent from another site is refused: its `Origin`
    must be one of the names above, and `Sec-Fetch-Site: cross-site` is refused outright;
  · `ZAELAR_API_TOKEN`, when set, lets a caller that presents it in `X-Zaelar-Token` through all of the above —
    the door for an operator who opened his engine to his network on purpose. Closed by default.

Cloud account process (`nucleo.account_routing`): the session is already established by `server/ingress.py`,
and the session is a cookie — which a browser attaches to a request another site makes. So a mutating request
there must come from the account's own site: `Origin` equal to `Host`, and never `Sec-Fetch-Site: cross-site`.

A request with no `Origin` header (a CLI, the daemon, the WhatsApp bridge, the engine calling itself) is not a
browser on another site and passes the origin rule; the peer and host rules still apply.

`decide` is a pure function of the request's facts, so the policy is testable without a server.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
from urllib.parse import urlparse

#: The names this engine answers to on its own machine (see `connectors/google/app.served_origins`).
LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "local.zaelar.com"})
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
TOKEN_ENV = "ZAELAR_API_TOKEN"
TOKEN_HEADER = "x-zaelar-token"

#: Starlette's in-process `TestClient` presents peer «testclient» and Host «testserver». A real socket always has
#: an IP for a peer, so this exact pair cannot come off the network; accepting it keeps the suites that drive the
#: whole app in-process from needing a disguise, without opening anything a request from outside can reach.
_IN_PROCESS = ("testclient", "testserver")


def _hostname(raw_host: str) -> str:
    h = (raw_host or "").strip().lower()
    if h.startswith("["):                                   # [::1]:44317
        return h[1:h.index("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def _is_loopback(peer: str) -> bool:
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def decide(*, path: str, method: str, peer: str, host: str, origin: str, fetch_site: str,
           token_given: str, token_set: str, cloud: bool, forwarded_host: str = "") -> tuple[bool, str]:
    """`(allowed, reason)` for one request. `reason` is a stable slug, never a header value."""
    if not path.startswith("/api/"):
        return True, "not_api"
    mutating = method.upper() in MUTATING
    if cloud:
        if not mutating:
            return True, "cloud_read"
        if (fetch_site or "").lower() == "cross-site":
            return False, "cross_site"
        # the account's own site, as the browser named it: `Host`, or the edge's `X-Forwarded-Host` when a proxy
        # rewrote it on the way in (not verified live against the platform's proxy — see the V2-778 log)
        names = {(host or "").strip().lower(), (forwarded_host or "").split(",")[0].strip().lower()} - {""}
        if origin and (urlparse(origin).netloc or "").lower() not in names:
            return False, "origin_not_host"
        return True, "cloud_same_site"
    if token_set and token_given and hmac.compare_digest(token_given, token_set):
        return True, "token"
    hostname = _hostname(host)
    if (peer, hostname) == _IN_PROCESS:
        return True, "in_process"
    if not _is_loopback(peer):
        return False, "not_loopback"
    if hostname not in LOCAL_NAMES:
        return False, "host_not_local"
    if mutating:
        if (fetch_site or "").lower() == "cross-site":
            return False, "cross_site"
        if origin and (urlparse(origin).hostname or "").lower() not in LOCAL_NAMES:
            return False, "origin_not_local"
    return True, "local"


def install(app) -> None:
    """Mount the guard. Added after ingress, so it is the OUTER middleware: a refusal costs no session lookup."""
    @app.middleware("http")
    async def _api_guard(request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        try:
            from nucleo import account_routing as _ar
            cloud = bool(_ar.is_account_routing_machine())
        except Exception:  # noqa: BLE001 — unknown deployment: the stricter, self-hosted rule
            cloud = False
        ok, reason = decide(
            path=path, method=request.method,
            peer=(request.client.host if request.client else "") or "",
            host=request.headers.get("host") or "", origin=request.headers.get("origin") or "",
            fetch_site=request.headers.get("sec-fetch-site") or "",
            token_given=request.headers.get(TOKEN_HEADER) or "", token_set=(os.getenv(TOKEN_ENV) or "").strip(),
            cloud=cloud, forwarded_host=request.headers.get("x-forwarded-host") or "")
        if ok:
            return await call_next(request)
        from loguru import logger
        from starlette.responses import JSONResponse
        logger.warning(f"api guard: refused ({reason}) {request.method} {path}")
        return JSONResponse({"error": reason}, status_code=403, headers={"Cache-Control": "no-store"})
