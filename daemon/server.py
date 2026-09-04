"""The daemon's HTTP surface: standard library, loopback, token-authenticated.

WHY `http.server` AND NOT FastAPI. The daemon has to become a single-file installer for macOS and Windows (P4),
and the engine's own venv is ~1.7 GB across ~394 packages. Every dependency added here is weight in that
installer and one more thing that can fail to import on a stranger's machine. P0 needs a handful of JSON routes
over loopback, and `ThreadingHTTPServer` does that with zero installs — so the daemon's `requirements.txt` is
empty for P0 and stays as close to empty as P2 allows.

WHY LOOPBACK IS NOT ENOUGH, and what is done about it. Binding 127.0.0.1 keeps the daemon off the network, and
that is where the reasoning usually stops. It should not: 127.0.0.1 is reachable by every other process on the
machine AND — the part that actually bites — by any web page the user has open, because a browser will happily
`fetch('http://127.0.0.1:45817/files/read')` from any site in the world. A daemon that serves the user's
documents to whoever asks first is a worse hole than the one it was built to close. Three guards, each of which
alone would be enough for the ordinary case and none of which is trusted alone:

  1. **A bearer token** on every route but `/health`, generated at first run and stored 0600 in `daemon.json`.
     The engine reads it from the same file. A web page cannot read that file.
  2. **Any request carrying `Origin` or `Sec-Fetch-Site` is refused outright.** Browsers always attach those on
     a cross-origin fetch; a server-side Python client never does. This holds even if the token leaked into a
     page, and it is the guard that makes the browser vector structurally impossible rather than merely
     unlikely.
  3. **No CORS headers are ever sent, and `OPTIONS` is refused.** A preflight that never succeeds means the
     browser will not even deliver the interesting requests.

The engine, which is the only intended caller, is a Python process on the same machine and satisfies all three
without doing anything special.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import HOST, PORT, VERSION, audit, config, files, permissions
from .permissions import Refusal

# Routes reachable without the token. `/health` says only that a daemon is running and what version it is —
# nothing about the user, their folders or their files — so the engine can poll it to paint the status icon
# before it has read the token, and the install wizard can tell "not installed" from "installed, not paired".
_PUBLIC = frozenset({"/health"})


class Handler(BaseHTTPRequestHandler):
    server_version = "zaelar-daemon/" + VERSION
    sys_version = ""            # do not advertise the Python version to anything that connects

    # ── plumbing ──────────────────────────────────────────────────────────────────────────────────────────

    def log_message(self, fmt: str, *args) -> None:      # noqa: A003 — BaseHTTPRequestHandler's name
        """Silence the default stderr access log. Operations are recorded in `audit.py`, which logs the thing
        that matters (which path, allowed or refused) instead of a request line."""
        return

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Never a CORS header. See the module docstring — their absence is guard 3.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:       # noqa: BLE001 — client hung up mid-write
            pass

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if n <= 0 or n > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8")) or {}
        except Exception:       # noqa: BLE001 — malformed body is an empty body; handlers refuse by argument
            return {}

    def _authorized(self, path: str) -> bool:
        """Guards 1 and 2. Order matters: the browser check runs FIRST, so a page that somehow holds the token
        is still refused, and refused for the right reason."""
        if self.headers.get("Origin") or self.headers.get("Sec-Fetch-Site"):
            return False
        if path in _PUBLIC:
            return True
        auth = (self.headers.get("Authorization") or "").strip()
        expected = config.token()
        if not expected:
            return False
        if not auth.lower().startswith("bearer "):
            return False
        # Constant-time: the token is a secret and a timing oracle on a loopback socket is a real one.
        import hmac
        return hmac.compare_digest(auth[7:].strip(), expected)

    def _caller(self) -> str:
        """Who is asking. Only `local` exists in P0; the relay (P3) will mark its own traffic so the audit log
        can tell the user's own engine from a cloud agent reaching in."""
        return "relay" if self.headers.get("X-Zaelar-Relay") else "local"

    # ── routing ───────────────────────────────────────────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:       # noqa: N802 — the framework's naming
        self._send(405, {"ok": False, "error": "no_cors", "message": "This daemon is not reachable from a browser."})

    def do_GET(self) -> None:           # noqa: N802
        self._route("GET", self.path.split("?", 1)[0])

    def do_POST(self) -> None:          # noqa: N802
        self._route("POST", self.path.split("?", 1)[0])

    def _route(self, method: str, path: str) -> None:
        if not self._authorized(path):
            self._send(401, {"ok": False, "error": "unauthorized",
                             "message": "This daemon only answers the Zaelar engine on this machine."})
            return
        caller = self._caller()
        try:
            payload = self._body() if method == "POST" else {}
            handler = _ROUTES.get((method, path))
            if handler is None:
                self._send(404, {"ok": False, "error": "unknown_route", "message": f"No route {method} {path}."})
                return
            result = handler(self, payload)
            self._send(200, result)
        except Refusal as r:
            # A refusal is a normal, expected answer with a reason attached — not a server failure. 403 with the
            # boundary named (V2-421/V2-507), so the engine can tell the user something true.
            audit.record(_op_of(path), caller=caller, path=str(payload.get("path") or "") or None,
                         outcome="refused", reason=r.code)
            self._send(403, r.as_dict())
        except Exception as e:  # noqa: BLE001 — anything unexpected is still an answer, never a hung socket
            audit.record(_op_of(path), caller=caller, outcome="error", reason=type(e).__name__)
            self._send(500, {"ok": False, "error": "internal", "message": str(e)})


def _op_of(path: str) -> str:
    return path.strip("/").replace("/", ".") or "root"


# ── handlers ──────────────────────────────────────────────────────────────────────────────────────────────

def _health(h: Handler, _payload: dict) -> dict:
    """Deliberately says nothing about the user. It is the only unauthenticated route, so what it reveals is
    what an unauthenticated caller may learn: that a daemon is here, and what it can do."""
    cfg = config.load()
    return {
        "ok": True,
        "daemon": "zaelar",
        "version": VERSION,
        "configured": bool(cfg.get("configured")),
        # What the engine may ask for. The browser capability arrives in P2 and the engine must not offer a
        # CAPTCHA hand-off before it is really there — a capability the engine assumes is a promise to the user.
        "capabilities": ["files.list", "files.read", "files.search"],
    }


def _permissions(h: Handler, _payload: dict) -> dict:
    cfg = config.load()
    return {"ok": True, "roots": permissions.roots(), "configured": bool(cfg.get("configured")),
            "candidates": permissions.candidates()}


def _grant(h: Handler, payload: dict) -> dict:
    roots = permissions.grant(str(payload.get("path") or ""))
    audit.record("permissions.grant", caller=h._caller(), path=str(payload.get("path") or ""), outcome="ok")
    return {"ok": True, "roots": roots}


def _revoke(h: Handler, payload: dict) -> dict:
    roots = permissions.revoke(str(payload.get("path") or ""))
    audit.record("permissions.revoke", caller=h._caller(), path=str(payload.get("path") or ""), outcome="ok")
    return {"ok": True, "roots": roots}


def _list(h: Handler, payload: dict) -> dict:
    out = files.list_dir(payload.get("path") or None, limit=int(payload.get("limit") or 500))
    audit.record("files.list", caller=h._caller(), path=out.get("path"), outcome="ok",
                 detail={"entries": len(out.get("entries") or [])})
    return out


def _read(h: Handler, payload: dict) -> dict:
    out = files.read_file(str(payload.get("path") or ""), max_bytes=int(payload.get("max_bytes") or 0)
                          or files.MAX_READ_BYTES)
    audit.record("files.read", caller=h._caller(), path=out.get("path"), outcome="ok",
                 detail={"bytes": len(out.get("text") or ""), "truncated": bool(out.get("truncated"))})
    return out


def _search(h: Handler, payload: dict) -> dict:
    out = files.search(str(payload.get("query") or ""), raw_path=payload.get("path") or None,
                       content=bool(payload.get("content")), limit=int(payload.get("limit") or 100))
    audit.record("files.search", caller=h._caller(), path=payload.get("path") or None, outcome="ok",
                 detail={"query": out.get("query"), "hits": len(out.get("hits") or []),
                         "stopped_early": out.get("stopped_early")})
    return out


def _audit(h: Handler, payload: dict) -> dict:
    return {"ok": True, "entries": audit.tail(int(payload.get("limit") or 200))}


_ROUTES = {
    ("GET", "/health"): _health,
    ("GET", "/permissions"): _permissions,
    ("POST", "/permissions/grant"): _grant,
    ("POST", "/permissions/revoke"): _revoke,
    ("POST", "/files/list"): _list,
    ("POST", "/files/read"): _read,
    ("POST", "/files/search"): _search,
    ("POST", "/audit"): _audit,
}


# ── lifecycle ─────────────────────────────────────────────────────────────────────────────────────────────

class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build(port: int | None = None) -> _Server:
    """Bind and return the server WITHOUT serving, so tests can drive it on an arbitrary port and callers can
    report a bind failure themselves instead of the process dying inside `serve_forever`."""
    cfg = config.load()
    return _Server((HOST, int(port or cfg.get("port") or PORT)), Handler)


def is_running(port: int | None = None) -> bool:
    """Is a daemon already listening? A plain TCP connect, the same test `scripts/zaelar.py` uses — never a
    process-name match, which has silently matched nothing on this very machine before."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, int(port or config.load().get("port") or PORT))) == 0


def serve(port: int | None = None) -> int:
    cfg = config.load()
    p = int(port or cfg.get("port") or PORT)
    if is_running(p):
        print(f"zaelar-daemon is already listening on {HOST}:{p}", flush=True)
        return 0
    try:
        srv = build(p)
    except OSError as e:
        print(f"zaelar-daemon could not bind {HOST}:{p} — {e}", file=sys.stderr, flush=True)
        return 1
    roots = permissions.roots()
    print(f"zaelar-daemon {VERSION} on http://{HOST}:{p}", flush=True)
    print(f"  folders: {', '.join(roots) if roots else '(none yet — the engine will ask)'}", flush=True)
    audit.record("daemon.start", outcome="ok", detail={"port": p, "roots": len(roots)})
    t = threading.Thread(target=srv.serve_forever, name="zaelar-daemon", daemon=True)
    t.start()
    try:
        t.join()
    except KeyboardInterrupt:
        print("\nzaelar-daemon stopping…", flush=True)
    finally:
        audit.record("daemon.stop", outcome="ok")
        srv.shutdown()
        srv.server_close()
    return 0
