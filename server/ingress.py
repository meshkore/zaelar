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
The list holds the app shell, its static assets and a liveness probe — bytes that are identical in
every process and belong to nobody.

The decision itself (`decide`) is a pure function of five inputs, so the interesting part is testable
without a server, a network or a clock.

Before 2026-08-13 the middleware this replaces called `call_next()` on all four of the refusal paths
above. That was not a theoretical weakness: a plain unauthenticated GET to the shared hostname
returned tenant data.
"""
from __future__ import annotations

import os

from loguru import logger

# --- what answers without a session -------------------------------------------------------------

# Exact paths. `/` is the app SHELL (an HTML file identical in every process, holding no data of
# anyone's); it also has to stay open because the platform's own HTTP health check fetches it, and a
# process that fails its health check stops receiving traffic altogether.
PUBLIC_EXACT = frozenset({"/", "/healthz", "/favicon.ico"})

# Prefixes. Static assets are byte-identical everywhere, so routing them is pointless and refusing
# them would only break the shell that is already public.
PUBLIC_PREFIXES = ("/static/",)

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


def decide(
    *,
    path: str,
    has_cookie: bool,
    resolver_configured: bool,
    outcome: str | None,
    target: str | None,
    mine: str | None,
) -> tuple[str, str]:
    """Pure admission decision → `(action, reason)`. `reason` is a stable, non-sensitive slug: it
    goes to logs and to the client, and it must never carry a token, a path or an internal URL.

    `outcome`/`target` are what the resolver said (`account_routing.RESOLVED` / `NO_SESSION` /
    `UNAVAILABLE`); they are only consulted once a cookie is present, so the common refusal costs no
    network at all."""
    from nucleo import account_routing as ar

    if is_public_path(path):
        return SERVE, "public_path"

    # A process that cannot ask "whose session is this?" cannot answer a tenant request either. This
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
        if is_public_path(path):
            return await call_next(request)

        resolver_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
        mine = ar.my_machine_id()
        token = request.cookies.get(ar.SESSION_COOKIE)

        outcome: str | None = None
        target: str | None = None
        if token and resolver_url and mine:
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
        )

        if action == SERVE:
            return await call_next(request)
        if action == REPLAY:
            from starlette.responses import Response

            return Response(status_code=307, headers={"fly-replay": f"instance={target}"})

        status = 401 if action == DENY else 503
        # Logged at debug for DENY: an internet-facing hostname collects these continuously, and a
        # warning per unauthenticated probe is a log flood, not a signal. UNAVAILABLE is the one that
        # means something is broken on our side, so that one is a warning.
        line = f"ingress: refused ({reason}) {request.method} {path} -> {status}"
        logger.warning(line) if status == 503 else logger.debug(line)
        return _refusal(status, reason, request)
