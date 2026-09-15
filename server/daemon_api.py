"""server/daemon_api.py — the engine's view of the Zaelar Local Daemon (V2-575 · P1).

WHY THE ENGINE PROXIES INSTEAD OF THE BROWSER CALLING 45817 DIRECTLY. Three problems disappear at once. The
page is served over https on a cloud account and the daemon speaks plain http, so a direct call is
mixed-content and the browser refuses it. A direct call is cross-origin, so it needs CORS headers the daemon
must never send — its whole browser defence is that it answers no page, ever (`daemon/security/guards.py`).
And the daemon's bearer token would have to reach JavaScript to be sent, which would put a credential that
reads the user's documents into a place any injected script can read. The engine already holds the token on
the server side, and it is the only thing that ever talks to 45817.

⚠️ WHAT THIS ROUTER DELIBERATELY DOES NOT EXPOSE: `files.list`, `files.read`, `files.search`. The browser has
no use for them — the UI shows which folders are granted, not what is inside them — and proxying them would
hand every page that can reach the engine exactly the capability the daemon spends five guards refusing. The
agent reads files SERVER-SIDE, in-process, never over this surface. Adding a file route here would undo
`zaelar-daemon-security.md` §3.1 through the engine's own front door.

SAME-ORIGIN IS ENFORCED HERE TOO, for the same reason. Without CORS a hostile page cannot READ our answer, but
it can still FIRE a `POST` it never reads — and `grant` is a state change, so a blind cross-site POST could add
a folder to the allowlist and the user would never see the request. `_same_origin()` is the guard; it is not
the daemon's (that one refuses every browser, and this surface's legitimate caller IS a browser) but the
narrower question a proxy can ask: is this page ours?

A CLOUD ENGINE CANNOT REACH THE DAEMON AT ALL, and says so rather than pretending. The daemon runs on the
user's computer; the cloud engine runs in a container somewhere else, and the path between them is the relay
(P3), which does not exist. So on a cloud account this router answers `reachable: false, local: false` and the
useful thing it still has is the DOWNLOAD — which is precisely the case the operator asked for: somebody
working against the cloud agent needs the installer, and the icon is where they get it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

router = APIRouter()

# Kept in sync with `daemon/__init__.py` by a test, and duplicated rather than imported for the same reason the
# daemon never imports the engine: these two halves must stay able to run without each other.
_DEFAULT_PORT = 45817
_TIMEOUT_S = 4.0

# Where a user gets the installer. Pinned to the daemon's OWN version tag rather than `releases/latest`, which
# follows whatever was released last — including an engine release carrying no daemon assets at all, and a link
# that 404s on the one screen whose entire job is handing somebody a file.
_RELEASE_BASE_DEFAULT = "https://github.com/meshkore/zaelar/releases/download"

_ASSETS = {
    "macos": {"artifact": "zaelar-daemon-macos", "installer": "zaelar-daemon-install-macos.sh",
              "checksums": "SHA256SUMS-macos"},
    "windows": {"artifact": "zaelar-daemon-windows.exe", "installer": "zaelar-daemon-install-windows.ps1",
                "checksums": "SHA256SUMS-windows"},
}

# ⚠️ THE ONE-LINE COMMAND IS THE MAIN PATH, and it is not a convenience for people who like terminals. macOS
# quarantine and the Windows Mark of the Web are written by whatever SAVED the file — a browser stamps it,
# `curl` and `Invoke-WebRequest` do not. So a daemon that arrives this way is never held by Gatekeeper and
# never raises the SmartScreen panel, on unsigned artifacts, with no Apple or Microsoft account and nothing to
# renew. The download buttons stay as a fallback for somebody who would rather see the file, and they are the
# ones that cost a security dialog.
#
# ⚠️ AND THE ARCHITECTURE PROBLEM IS WHY A BUTTON CANNOT BE THE MAIN PATH. Apple Silicon and Intel need
# different binaries, a user-agent does not reliably say which, and picking wrong fails with "bad CPU type in
# executable". The script reads `uname -m` and is simply right.
_BOOTSTRAP_BASE_DEFAULT = "https://raw.githubusercontent.com/meshkore/zaelar/main/daemon/packaging"

_BOOTSTRAP = {
    "macos": {"script": "get.sh", "command": "curl -fsSL {base}/get.sh | bash"},
    "windows": {"script": "get.ps1", "command": "irm {base}/get.ps1 | iex"},
}


# ── where the daemon is, without creating anything ────────────────────────────────────────────────────────

def _state_dir() -> Path:
    """`config/daemon/` under the workspace — the same rule `daemon/paths.py` uses, resolved here WITHOUT
    calling it. `paths.state_dir()` creates the directory and `config.load()` would mint a token into it, and an
    engine that has no daemon must not leave a credential file lying around on a cloud Volume just because
    somebody opened the status icon."""
    try:
        from nucleo import workspace
        root = Path(workspace.root())
    except Exception:       # noqa: BLE001 — the engine's own workspace module is not this router's business
        root = Path(os.getenv("ZAELAR_WORKSPACE") or Path(__file__).resolve().parent.parent)
    return root / "config" / "daemon"


def _daemon_config() -> dict:
    """What `daemon.json` says, or `{}` when there is none. Missing is the NORMAL case (nobody has installed
    it), so it is not an error and never logged as one."""
    try:
        data = json.loads((_state_dir() / "daemon.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:       # noqa: BLE001 — absent, unreadable or corrupt all mean the same thing here
        return {}


def _is_cloud() -> bool:
    try:
        from config import cloud_account
        return bool(cloud_account.is_cloud_account())
    except Exception:       # noqa: BLE001
        return False


def _port(cfg: dict) -> int:
    try:
        port = int(cfg.get("port") or _DEFAULT_PORT)
    except (TypeError, ValueError):
        return _DEFAULT_PORT
    return port if 1 <= port <= 65535 else _DEFAULT_PORT


async def _call(cfg: dict, path: str, payload: dict | None = None) -> tuple[int, dict]:
    """One request to the daemon. Returns `(status, body)`; `(0, {})` when it could not be reached at all, which
    is what "not installed" and "not running" both look like from here and neither is an error."""
    port = _port(cfg)
    token = str(cfg.get("token") or "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, trust_env=False) as client:
            if payload is None:
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(url, headers=headers, json=payload)
        try:
            body = response.json()
        except Exception:   # noqa: BLE001
            body = {}
        return response.status_code, body if isinstance(body, dict) else {}
    except Exception:       # noqa: BLE001 — refused, timed out, no daemon: all "not reachable"
        return 0, {}


# ── the guard ─────────────────────────────────────────────────────────────────────────────────────────────

def _same_origin(request: Request) -> bool:
    """Our own page, or something that is not a browser at all.

    `Sec-Fetch-Site` is the direct answer when the browser sends it. `Origin` is the fallback, compared against
    the `Host` the request arrived on rather than a configured hostname — the engine is reached as
    `localhost:43917`, as `local.zaelar.com`, and as whatever a cloud account resolves to, and a guard that
    only knew one of those would lock the user out of their own interface, which is the failure direction that
    never shows up in a leak test."""
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        host = (request.headers.get("host") or "").strip().lower()
        return bool(host) and urlsplit(origin).netloc.lower() == host
    return True


_CROSS_SITE = JSONResponse({"ok": False, "error": "cross_origin"}, status_code=403)


# ── downloads ─────────────────────────────────────────────────────────────────────────────────────────────

def _daemon_version() -> str:
    """The version this engine's source tree carries, read from `daemon/__init__.py` WITHOUT importing it. It
    names the release tag the download links point at, so it has to be readable on a cloud engine where the
    daemon package may not even be on the path."""
    try:
        text = (Path(__file__).resolve().parent.parent / "daemon" / "__init__.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("VERSION"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:       # noqa: BLE001
        pass
    return ""


def _downloads(version: str) -> dict:
    base = (os.getenv("ZAELAR_DAEMON_DOWNLOAD_BASE") or "").strip().rstrip("/")
    tag = f"daemon-v{version}" if version else ""
    if not base:
        base = f"{_RELEASE_BASE_DEFAULT}/{tag}" if tag else ""
    boot = (os.getenv("ZAELAR_DAEMON_BOOTSTRAP_BASE") or _BOOTSTRAP_BASE_DEFAULT).rstrip("/")
    out: dict = {"tag": tag, "platforms": {}}
    if not base:
        return out
    for name, assets in _ASSETS.items():
        entry = {key: f"{base}/{filename}" for key, filename in assets.items()}
        entry["bootstrap"] = f"{boot}/{_BOOTSTRAP[name]['script']}"
        entry["command"] = _BOOTSTRAP[name]["command"].format(base=boot)
        out["platforms"][name] = entry
    return out


def _guess_platform(request: Request) -> str:
    """Which installer to put in front of this person first. The client's own user-agent, because the ENGINE's
    platform is the wrong answer on a cloud account (a Linux container) and on a self-hoster browsing from a
    second machine."""
    agent = (request.headers.get("user-agent") or "").lower()
    if "windows" in agent:
        return "windows"
    if "mac" in agent or "darwin" in agent:
        return "macos"
    if not agent:
        return "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "")
    return ""


# ── routes ────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/api/daemon/status")
async def daemon_status(request: Request):
    """Everything the icon and the wizard need, in one call — deliberately, because the icon polls it and a
    second round trip per poll buys nothing.

    `state` is the icon's colour and is computed HERE rather than in JavaScript: "running but the user has
    chosen no folders" is a warning and "running with folders" is fine, and that judgement should not live in
    two places where one can drift."""
    cfg = _daemon_config()
    cloud = _is_cloud()
    version = _daemon_version()
    payload: dict = {
        "ok": True,
        "local": not cloud,
        "installed": bool(cfg),
        "reachable": False,
        "running": False,
        "configured": False,
        "version": "",
        "expected_version": version,
        "outdated": False,
        "capabilities": [],
        "roots": [],
        "candidates": [],
        "port": _port(cfg),
        "platform": _guess_platform(request),
        "downloads": _downloads(version),
    }
    # A cloud engine is not on the user's machine, so probing 127.0.0.1 would either time out or — worse —
    # reach a daemon belonging to whoever else is on that host. It does not probe at all.
    if cloud:
        payload["state"] = "remote"
        return JSONResponse(payload)
    # ⚠️ NO CONFIG MEANS NO DAEMON OF OURS, and the probe is skipped rather than attempted. `/health` is the one
    # route that answers without a token, so probing anyway would report `reachable: true` on the strength of a
    # daemon this engine cannot authenticate to — a green icon over a surface where every real call 401s, which
    # is worse than a grey one. A daemon that has actually run always wrote `daemon.json` (it mints its token at
    # boot), so requiring it locks nobody out.
    if not cfg.get("token"):
        payload["state"] = "off"
        return JSONResponse(payload)
    status, health = await _call(cfg, "/health")
    if status == 200 and health.get("ok"):
        payload.update({
            "reachable": True, "running": True,
            "version": str(health.get("version") or ""),
            "configured": bool(health.get("configured")),
            "capabilities": list(health.get("capabilities") or []),
        })
        payload["outdated"] = bool(version and payload["version"] and payload["version"] != version)
        # GET, not POST: `/permissions` is a read in the daemon's table and a POST there is a 405.
        pstatus, perms = await _call(cfg, "/permissions")
        if pstatus == 200 and perms.get("ok"):
            payload["roots"] = list(perms.get("roots") or [])
            payload["candidates"] = list(perms.get("candidates") or [])
        payload["state"] = "warn" if (payload["outdated"] or not payload["roots"]) else "ok"
    else:
        payload["state"] = "off"
    return JSONResponse(payload)


@router.post("/api/daemon/permissions/grant")
async def daemon_grant(request: Request, body: dict = Body(default={})):
    if not _same_origin(request):
        return _CROSS_SITE
    return await _permissions(request, "/permissions/grant", body)


@router.post("/api/daemon/permissions/revoke")
async def daemon_revoke(request: Request, body: dict = Body(default={})):
    if not _same_origin(request):
        return _CROSS_SITE
    return await _permissions(request, "/permissions/revoke", body)


async def _permissions(_request: Request, path: str, body: dict) -> JSONResponse:
    """A folder in, the new allowlist out. The daemon's refusal text is passed through UNCHANGED: it names the
    boundary ("that is your home folder", "that folder holds credentials") and rewriting it here would turn a
    sentence the user can act on into a generic failure — the V2-421/V2-507 lesson, and the reason the daemon
    bothers to produce one."""
    if _is_cloud():
        return JSONResponse({"ok": False, "error": "no_daemon_from_cloud"}, status_code=409)
    cfg = _daemon_config()
    if not cfg:
        return JSONResponse({"ok": False, "error": "not_installed"}, status_code=409)
    folder = body.get("path")
    status, result = await _call(cfg, path, {"path": folder if isinstance(folder, str) else ""})
    if status == 0:
        return JSONResponse({"ok": False, "error": "not_running"}, status_code=409)
    return JSONResponse(result, status_code=status)
