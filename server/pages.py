"""Screen routes (HTML). Two self-contained shells under frontend/: the desktop app (`/`) and the mobile
PWA (`/m`, V2-124). Plus the PWA's two root-served files, which have to answer from the root — see below."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .common import ZAELAR_DIR

router = APIRouter()

FRONTEND = os.path.join(ZAELAR_DIR, "frontend")


def front(*parts: str) -> str:
    return os.path.join(FRONTEND, *parts)


@router.get("/")
async def home():
    # no-store so a reload always gets the latest UI (avoids running stale cached JS)
    return FileResponse(front("index.html"), headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/healthz")
async def healthz():
    """LIVENESS only: "this process is answering HTTP". Deliberately says nothing else — it is one of
    the few paths a supervisor can reach without a session (server/ingress.py), so anything it
    reported would be readable by anyone who can reach the port. Whether the process is READY to do
    work is a different question with a different answer (/api/status, behind admission)."""
    return {"ok": True}


# ── THE MOBILE SHELL (V2-124) ────────────────────────────────────────────────────────────────────────────────
# Three routes, and all three are byte-identical on every Machine — which is exactly the test server/ingress.py
# applies before a path may answer without a session (see its PUBLIC_EXACT allowlist). No tenant data crosses here.


@router.get("/m")
async def mobile():
    """The mobile PWA shell. A DIFFERENT shell, not `/` with media queries: its own stylesheet, its own entry
    module, its own surfaces (frontend/mobile/). What it shares with the desktop is the engine underneath.

    `no-store`, same as `/` and for the same reason: a reload must never execute stale JavaScript. The service
    worker is built around this too — it never caches the shell (frontend/mobile/sw.js)."""
    return FileResponse(front("mobile", "index.html"), headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/manifest.webmanifest")
async def manifest():
    """PWA identity: name, colors, icons, `scope`/`start_url`. Served from the ROOT because a manifest's scope has
    to be reachable from where the manifest lives, and because the browser fetches it before anything else — long
    before any session exists. Cached briefly: it changes on release, not per request."""
    return FileResponse(front("mobile", "manifest.webmanifest"),
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sw.js")
async def service_worker():
    """The service worker, served from the ROOT — not from /static/ — because a worker can only control its own
    directory downwards: one served from /static/mobile/ could never see a navigation to /m.

    `Service-Worker-Allowed: /` is what lets it register with `scope: "/"` from this path.
    `no-cache` on the worker script itself matters more than usual: a stale worker is a shell that decides how
    every navigation is answered, and it would outlive the deploy that tried to replace it."""
    return FileResponse(front("mobile", "sw.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@router.get("/debug")
async def debug_page():
    return FileResponse(front("pages", "debug.html"), headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/api/brain")
async def brain():
    """The brain active for this run — "nucleo" (zaelar's own «Colmena» brain) by default, or a baseline
    ("direct"/"local"). The UI uses it to decide which brain-specific affordances to show."""
    from config.v2 import active_brain
    return {"brain": active_brain()}
