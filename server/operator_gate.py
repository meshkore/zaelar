"""server/operator_gate.py — a worker's request is never the operator's click (2026-10-14).

## Why

`POST /widgets/{id}/action` is recorded as HIS click (`provenance.note(wid, "user")`), and the same holds for every
other route his screen calls: a message sent from the messaging card, a contact, an agenda row, a setting, a
spoken turn injected through `/api/flash/say`. A background worker has Bash on the same machine, so a `curl` to
any of them was admitted as him, skipping `/api/worker/act` and its consent gate (`nucleo/on_his_behalf.py`,
`worker_policy.classify_act`). Only a line in the worker's prompt said not to.

## The rule (self-hosted engine)

Every MUTATING request (POST/PUT/PATCH/DELETE) is an operator route unless it is one of the worker's own doors
(`WORKER_DOORS`, each with its own per-task token or policy). An operator route is admitted only for:

  · a caller presenting the UI credential (`server/ui_session.py`: per-boot, memory-only, HttpOnly cookie) — the
    fast path every click of his page takes;
  · a process on this machine that the engine did NOT spawn (`server/peer_process.py` says OUTSIDE): his browser
    before its cookie was minted, his terminal, the test harness. Such a caller is minted the cookie;
  · a remote caller presenting `ZAELAR_API_TOKEN` (the door `server/api_guard.py` already opens on purpose).

A worker — or anything the engine spawned, the agent's own Chromium included — is refused, and so is a socket the
engine cannot attribute. The app shells (`GET /`, `GET /m`) mint the cookie the same way, so his page holds it from
its first click.

Cloud account process: skipped. Admission there is the account session (`server/ingress.py`), which a worker inside
the Machine does not have; and a per-boot secret could not span the Machines behind one hostname.
Starlette's in-process TestClient pair is admitted, as in `api_guard`: it cannot come off a socket.

`decide` is a pure function of the request's facts; the middleware only gathers them.
"""
from __future__ import annotations

import asyncio
import hmac
import os

from server import api_guard, peer_process, ui_session

#: Mutating routes a worker is MEANT to call — each verifies the worker on its own terms (per-task token, the act
#: policy). Everything else that mutates is the operator's.
WORKER_DOORS = ("/api/worker/", "/api/agent/report", "/api/navegador/act", "/api/memory/recall",
                "/api/memory/remember", "/api/search/")
SHELLS = frozenset({"/", "/m"})


def is_operator_route(path: str, method: str) -> bool:
    return method.upper() in api_guard.MUTATING and not path.startswith(WORKER_DOORS)


def decide(*, path: str, method: str, cloud: bool, in_process: bool, holds_ui: bool, kind: str | None,
           peer_loopback: bool, token_ok: bool) -> tuple[bool, str, bool]:
    """`(allowed, reason, mint_cookie)`. `kind` is `peer_process`'s verdict, None when it was not needed."""
    if method.upper() == "GET" and path in SHELLS:
        return True, "shell", not (cloud or in_process or holds_ui) and kind == peer_process.OUTSIDE
    if not is_operator_route(path, method):
        return True, "not_operator_route", False
    if cloud:
        return True, "cloud_session", False
    if in_process:
        return True, "in_process", False
    if holds_ui:
        return True, "ui_session", False
    if kind == peer_process.OUTSIDE:
        return True, "operator_process", True
    if kind == peer_process.WORKER:
        return False, "worker_is_not_the_operator", False
    if kind == peer_process.SELF:
        return False, "engine_is_not_the_operator", False
    if token_ok and not peer_loopback:
        return True, "token", False
    return False, "peer_unattributed", False


def _cloud() -> bool:
    try:
        from nucleo import account_routing as _ar
        return bool(_ar.is_account_routing_machine())
    except Exception:  # noqa: BLE001 — unknown deployment: the stricter, self-hosted rule
        return False


async def _kind(request) -> str:
    from loguru import logger
    client = request.client
    server_port = int((request.scope.get("server") or ("", 0))[1] or 0)
    try:
        return await asyncio.to_thread(peer_process.kind_of, client.host if client else "",
                                       int(client.port or 0) if client else 0, server_port)
    except Exception:  # noqa: BLE001 — cannot attribute the caller: refused (UNKNOWN), and said
        logger.opt(exception=True).warning("operator gate: peer lookup failed")
        return peer_process.UNKNOWN


def install(app) -> None:
    """Mount the gate. Installed between ingress and `api_guard`, so the origin/host checks still run first."""
    @app.middleware("http")
    async def _operator_gate(request, call_next):
        path, method = request.url.path, request.method.upper()
        if not (method == "GET" and path in SHELLS) and not is_operator_route(path, method):
            return await call_next(request)
        peer = (request.client.host if request.client else "") or ""
        cloud = _cloud()
        in_process = (peer, api_guard._hostname(request.headers.get("host") or "")) == api_guard._IN_PROCESS
        holds = ui_session.holds(request.cookies.get(ui_session.COOKIE))
        kind = None if (cloud or in_process or holds) else await _kind(request)
        token_set = (os.getenv(api_guard.TOKEN_ENV) or "").strip()
        token_given = request.headers.get(api_guard.TOKEN_HEADER) or ""
        ok, reason, mint = decide(
            path=path, method=method, cloud=cloud, in_process=in_process, holds_ui=holds, kind=kind,
            peer_loopback=api_guard._is_loopback(peer),
            token_ok=bool(token_set and token_given and hmac.compare_digest(token_given, token_set)))
        if not ok:
            from loguru import logger
            from starlette.responses import JSONResponse
            logger.warning(f"operator gate: refused ({reason}) {method} {path}")
            return JSONResponse({"error": reason}, status_code=403, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if mint:
            ui_session.mint(response)
        return response
