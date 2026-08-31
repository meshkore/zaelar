#
# client.py — HTTP client for the MeshKore daemon (Architect remote control).
#
# The daemon is a SINGLE shared service on this machine (NOT per-project) that serves every cluster project. This
# client speaks its REST API: list/create projects and talk to each project's architect-master (async ask + poll).
# Daemon rules this client respects: Authorization on every request, X-MeshKore-Project for routing, and ONE turn at
# a time per project (429 → ArchitectBusy).
#
# Config (.env, gitignored — the token is NEVER committed or shown):
#   ARCHITECT_URL    — daemon base URL (default: https://127.0.0.1:5573)
#   ARCHITECT_TOKEN  — remote-control bearer token (the operator rotates it from the cockpit if it leaks)
#
import os
from urllib.parse import urlparse

import aiohttp


class ArchitectError(RuntimeError):
    pass


class ArchitectBusy(ArchitectError):
    """The project manager already has a turn in flight (429) — wait and retry, never in parallel."""


def base_url() -> str:
    # V2-083: dynamic store wins (configurable from Connectors); env as power-user fallback; default loopback.
    try:
        from config import connectors as _cfg
        u = str((_cfg.get("architect") or {}).get("url") or "").strip()
        if u:
            return u.rstrip("/")
    except Exception:
        pass
    return os.getenv("ARCHITECT_URL", "https://127.0.0.1:5573").rstrip("/")


def token() -> str:
    # V2-083: the token lives in the dynamic connector store (config/connectors.json), manageable/revocable from the
    # Connectors tab. `.env` (ARCHITECT_TOKEN) remains only as a power-user/headless fallback.
    try:
        from config import connectors as _cfg
        t = str((_cfg.get("architect") or {}).get("token") or "").strip()
        if t:
            return t
    except Exception:
        pass
    return (os.getenv("ARCHITECT_TOKEN") or "").strip()


def configured() -> bool:
    return bool(token())


def _ssl():
    # The daemon uses self-signed TLS: relax verification ONLY on loopback (its normal deployment).
    host = (urlparse(base_url()).hostname or "").lower()
    return False if host in ("127.0.0.1", "localhost", "::1") else None


def _headers(project: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token()}"}
    if project:
        h["X-MeshKore-Project"] = project
    return h


async def _request(method: str, path: str, *, project: str | None = None,
                   body: dict | None = None, timeout: float = 20.0):
    if not configured():
        raise ArchitectError("ARCHITECT_TOKEN no configurado en .env")
    to = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=to, connector=aiohttp.TCPConnector(ssl=_ssl())) as s:
        async with s.request(method, base_url() + path, headers=_headers(project), json=body) as r:
            if r.status == 429:
                raise ArchitectBusy(f"{path}: el proyecto ya tiene un turno en curso (429)")
            if r.status in (401, 403):
                raise ArchitectError(f"{path}: acceso revocado o token rotado ({r.status}) — "
                                     "pide al operador el token nuevo (cockpit → Config → Remote control)")
            if r.status >= 400:
                raise ArchitectError(f"{path}: HTTP {r.status} · {(await r.text())[:200]}")
            return await r.json()


async def list_projects() -> list[dict]:
    """Live projects in the daemon: [{id, name, path}]. Changes — relist whenever in doubt."""
    data = await _request("GET", "/projects")
    return data if isinstance(data, list) else (data or {}).get("projects", [])


async def ask(project: str, text: str) -> dict:
    """Send the operator intent to the project's architect-master. → 202 {"request_id", "conv"}."""
    return await _request("POST", "/team/architect-master/ask", project=project, body={"text": text})


async def poll(project: str, request_id: str) -> dict:
    """Ask status: {"status": "queued|running|done|error", "result_text": "..."}."""
    return await _request("GET", f"/team/requests/{request_id}", project=project)


async def create_project(parent: str, name: str) -> dict:
    """Create a new project (folder + MeshKore standard + default team) and register it in the daemon."""
    return await _request("POST", "/projects", body={"parent": parent, "name": name}, timeout=120.0)
