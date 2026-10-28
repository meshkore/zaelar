"""server/ingress.py — request ADMISSION for a process that takes part in session routing.

A single-process install serves whoever reaches it: the operator runs it, the operator owns it, and
the network boundary is the machine it runs on. That assumption stops holding the moment several
processes share ONE public hostname and each one holds a different person's data — then "whichever
process the edge happened to pick answered the request" is not a routing detail, it is the wrong
process answering.

So on a process that takes part in session routing (`nucleo.account_routing.is_account_routing_machine`)
a request is served only after this process has ESTABLISHED that the request's session belongs to it.
Everything else is refused. In particular:

  * no session credential  →  refuse (401), never "serve locally and hope this is the right process";
  * a credential this process cannot resolve  →  refuse (503). An unreachable resolver, a timeout or
    a rejected lookup is the ABSENCE of an answer, and the absence of an answer is not permission;
  * a credential that resolves ELSEWHERE  →  hand the request to that process, do not answer it here;
  * a credential that resolves HERE  →  serve.

`ZAELAR_INGRESS_PUBLIC` (below) is the whole list of paths that answer without a session, and it is
an ALLOWLIST on purpose: a route added tomorrow is closed until someone puts it here deliberately.
The list holds the app shells (desktop and mobile), the mobile PWA's manifest and service worker, the
static assets and a liveness probe — bytes that belong to nobody. They are identical only within one
build, so when such a request carries a session it is still handed to the process that owns it.

The decision itself (`decide`) is a pure function of five inputs, so the interesting part is testable
without a server, a network or a clock.
"""
from __future__ import annotations

import os

from loguru import logger

# --- what answers without a session -------------------------------------------------------------

# Exact paths. `/` is the app SHELL (an HTML file identical in every process, holding no data of
# anyone's); it also has to stay open because the platform's own HTTP health check fetches it, and a
# process that fails its health check stops receiving traffic altogether.
# `/m` is the MOBILE shell (V2-124) — a second HTML file, held by nobody, identical in every process, exactly
# like `/`. `/manifest.webmanifest` and `/sw.js` are its PWA plumbing and must be served from the root: a
# manifest's scope has to be reachable from where it lives, and a service worker can only control its own
# directory downwards. All three are build constants; adding them opens no account data, which is the only
# question this allowlist asks.
PUBLIC_EXACT = frozenset({
    "/", "/healthz", "/favicon.ico",
    "/m", "/manifest.webmanifest", "/sw.js",
})

# Prefixes. Static assets belong to nobody, so refusing them would only break the shell that is already public.
PUBLIC_PREFIXES = ("/static/",)

# Public bytes are identical only between processes running the SAME build. Processes on one hostname are
# upgraded one at a time, so a shell fetched from one build and its modules from another is a page that
# does not load (measured live 2026-10-22: a module new in the release answered 404 from a process still on
# the previous build, and the shell hung on its boot veil). So a public request that CARRIES a session goes
# to the process that owns it, like any other request; without a session it is served wherever it lands.
# `/healthz` is the platform's probe of THIS process and is never handed over.
_NEVER_REPLAYED = frozenset({"/healthz"})

# A shared edge cache keys these paths by URL alone, so it would hand one build's bytes (or one build's 404)
# to a visitor whose process runs another. The edge must not keep them; browsers still revalidate by ETag.
EDGE_NO_STORE = {"CDN-Cache-Control": "no-store"}

# Decisions `decide` can return.
SERVE = "serve"              # this process owns the request
REPLAY = "replay"            # another process owns it — hand it over
DENY = "deny"                # no acceptable session credential (401)
UNAVAILABLE = "unavailable"  # cannot establish ownership right now (503)


def is_public_path(path: str) -> bool:
    """Whether `path` answers without a session. Prefix membership is checked on the RAW path, so a
    query string or a longer segment cannot smuggle a private route past the allowlist."""
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def is_own_worker_door(path: str, peer_loopback: bool) -> bool:
    """A worker this process spawned, calling one of its own doors back over loopback (V2-789).

    The engine's workers talk to their engine through `ZAELAR_BASE` (`nucleo.engine_url`, a loopback address):
    `cli.report`, `cli.nav`, `cli.mem`, `cli.widget`, the worker bridge. They hold no session cookie and never
    can — the session belongs to the browser — so every such call was refused as `no_session` (401) and the
    worker lost its reports and its browser. A loopback peer IS this process's own machine, so «whose session
    is this?» has only one answer, and the doors (`operator_gate.WORKER_DOORS`) each verify the worker on their
    own terms (per-task id/token, the act policy). Only those doors: a loopback caller gets no operator route."""
    if not peer_loopback:
        return False
    from server.operator_gate import WORKER_DOORS
    return path.startswith(WORKER_DOORS)


def decide(
    *,
    path: str,
    has_cookie: bool,
    resolver_configured: bool,
    outcome: str | None,
    target: str | None,
    mine: str | None,
    peer_loopback: bool = False,
) -> tuple[str, str]:
    """Pure admission decision → `(action, reason)`. `reason` is a stable, non-sensitive slug: it
    goes to logs and to the client, and it must never carry a token, a path or an internal URL.

    `outcome`/`target` are what the resolver said (`account_routing.RESOLVED` / `NO_SESSION` /
    `UNAVAILABLE`); they are only consulted once a cookie is present, so the common refusal costs no
    network at all."""
    from nucleo import account_routing as ar

    if is_public_path(path):
        # Same build as the shell that asked for it: hand it over when the session lives elsewhere. Any
        # other outcome serves it here — these bytes hold no one's data, so an unanswered lookup is no
        # reason to refuse them.
        if (path not in _NEVER_REPLAYED and has_cookie and mine and outcome == ar.RESOLVED
                and target and target != mine):
            return REPLAY, "session_owned_elsewhere"
        return SERVE, "public_path"

    if is_own_worker_door(path, peer_loopback):
        return SERVE, "own_worker_door"

    # A process that cannot ask "whose session is this?" cannot answer an account request either. This
    # used to serve the request; a missing environment variable was silently the most permissive
    # configuration available.
    if not resolver_configured or not mine:
        return UNAVAILABLE, "resolver_not_configured"

    if not has_cookie:
        return DENY, "no_session"

    if outcome == ar.UNAVAILABLE:
        return UNAVAILABLE, "session_unverifiable"
    if outcome == ar.NO_SESSION:
        return DENY, "session_not_recognized"
    if outcome == ar.RESOLVED and target:
        return (SERVE, "session_owned_here") if target == mine else (REPLAY, "session_owned_elsewhere")

    # Unreachable with a well-behaved resolver; closed anyway, because the alternative is to guess.
    return UNAVAILABLE, "session_unverifiable"


# --- the middleware -----------------------------------------------------------------------------


def _entry_url() -> str:
    """Where a browser that arrived without a session should be sent, when the deployment names one.
    A server-side value, never anything the request can influence — otherwise this would be an open
    redirect wearing a helpful face."""
    return (os.getenv("ZAELAR_INGRESS_ENTRY_URL") or "").strip()


def _wants_html(request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


def _refusal(status: int, reason: str, request):
    """A refusal says only what the caller needs to change course: a slug, never why the process
    thinks so. `Cache-Control: no-store` matters — a cached 401 would survive the visitor logging in."""
    from starlette.responses import JSONResponse, RedirectResponse

    headers = {"Cache-Control": "no-store"}
    if status == 503:
        headers["Retry-After"] = "5"
    if status == 401 and _wants_html(request) and _entry_url():
        return RedirectResponse(_entry_url(), status_code=302, headers=headers)
    return JSONResponse({"error": reason}, status_code=status, headers=headers)


def install(app) -> None:
    """Mount the admission gate. A no-op at request time on any process that is not part of session
    routing — `is_account_routing_machine()` is a pair of env reads, so a single-process install pays
    one branch and nothing else."""

    @app.middleware("http")
    async def _ingress(request, call_next):
        from nucleo import account_routing as ar

        if not ar.is_account_routing_machine():
            return await call_next(request)

        path = request.url.path
        public = is_public_path(path)
        resolver_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
        mine = ar.my_machine_id()
        token = request.cookies.get(ar.SESSION_COOKIE)

        if public and (path in _NEVER_REPLAYED or not token):
            response = await call_next(request)
            response.headers.update(EDGE_NO_STORE)
            return response

        from server import api_guard
        peer_loopback = api_guard._is_loopback((request.client.host if request.client else "") or "")

        outcome: str | None = None
        target: str | None = None
        if token and resolver_url and mine and not is_own_worker_door(path, peer_loopback):
            outcome, target = await ar.resolve_session_machine(
                token, control_plane_url=resolver_url
            )

        action, reason = decide(
            path=path,
            has_cookie=bool(token),
            resolver_configured=bool(resolver_url),
            outcome=outcome,
            target=target,
            mine=mine,
            peer_loopback=peer_loopback,
        )

        if action == SERVE:
            response = await call_next(request)
            if public:
                response.headers.update(EDGE_NO_STORE)
            return response
        if action == REPLAY:
            from starlette.responses import Response

            return Response(status_code=307, headers={"fly-replay": f"instance={target}", **EDGE_NO_STORE})

        status = 401 if action == DENY else 503
        # Logged at debug for DENY: an internet-facing hostname collects these continuously, and a
        # warning per unauthenticated probe is a log flood, not a signal. UNAVAILABLE is the one that
        # means something is broken on our side, so that one is a warning.
        line = f"ingress: refused ({reason}) {request.method} {path} -> {status}"
        logger.warning(line) if status == 503 else logger.debug(line)
        return _refusal(status, reason, request)
