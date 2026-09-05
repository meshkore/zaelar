"""Binding, serving and stopping — the daemon's life as a process.

WHY `http.server` AND NOT A FRAMEWORK. This has to become a single-file installer for macOS and Windows, and
every dependency added here is weight in that installer and one more thing that can fail to import on a
stranger's machine. A handful of JSON routes over loopback is what `ThreadingHTTPServer` is for, so the
daemon's `requirements.txt` is empty and stays as close to empty as the browser hand-off allows.

BOUNDED CONCURRENCY IS A GUARD, NOT TUNING. `ThreadingHTTPServer` starts a thread per connection and will
happily start ten thousand. Anything running as this user can open sockets faster than they finish, and the
failure is not a crash — it is the machine grinding while the daemon still technically answers. Past the cap the
socket is closed immediately: a refused connection is a fact the caller can act on, an exhausted machine is not.
"""
from __future__ import annotations

import socket
import sys
import threading
from http.server import ThreadingHTTPServer

from .. import HOST, PORT, VERSION, audit, config
from ..fs import roots as folders
from .handler import Handler
from .routes import TABLE

# Generous for one engine talking to one daemon, low enough that a flood is bounded long before the machine is.
MAX_CONNECTIONS = 64


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler_cls):
        self._live_lock = threading.Lock()
        self._live = 0
        super().__init__(address, handler_cls)

    def process_request(self, request, client_address):
        with self._live_lock:
            if self._live >= MAX_CONNECTIONS:
                over_capacity = True
            else:
                self._live += 1
                over_capacity = False
        if over_capacity:
            try:
                request.close()
            except Exception:   # noqa: BLE001 — the peer may already be gone
                pass
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request):
        try:
            super().shutdown_request(request)
        finally:
            with self._live_lock:
                self._live = max(0, self._live - 1)


def resolve_port(port: int | None) -> int:
    """An explicitly passed port WINS, including 0.

    `port or cfg["port"]` is the obvious spelling and it is wrong, because **0 is falsy**: `build(port=0)` —
    the "let the OS pick a free one" idiom every test uses — silently fell through to the configured port
    instead. That made the guard tests bind the REAL daemon's port, so they passed only while the operator's
    daemon happened to be down, and turned red the day it started automatically. `is not None` is the whole
    fix, and it is why this is a named function rather than three copies of the same expression.
    """
    if port is not None:
        return int(port)
    return int(config.load().get("port") or PORT)


def build(port: int | None = None) -> _Server:
    """Bind and return the server WITHOUT serving, so tests can drive it on an arbitrary port and callers can
    report a bind failure themselves instead of the process dying inside `serve_forever`.

    The handler is subclassed per server rather than configured globally: the Host guard has to compare against
    the port this server actually bound, and with `port=0` that number does not exist until after the bind. A
    class attribute set on the shared `Handler` would mean two servers in one process (which is exactly what the
    test suite is) silently checking each other's port."""
    server = _Server((HOST, resolve_port(port)), Handler)
    bound = int(server.server_address[1])
    server.RequestHandlerClass = type(
        "BoundHandler", (Handler,), {"bound_port": bound, "routes": TABLE},
    )
    return server


def is_running(port: int | None = None) -> bool:
    """Is a daemon already listening? A plain TCP connect, the same test `scripts/zaelar.py` uses — never a
    process-name match, which has silently matched nothing on this very machine before."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex((HOST, resolve_port(port))) == 0


def serve(port: int | None = None) -> int:
    resolved = resolve_port(port)
    if is_running(resolved):
        print(f"zaelar-daemon is already listening on {HOST}:{resolved}", flush=True)
        return 0
    try:
        server = build(resolved)
    except OSError as e:
        print(f"zaelar-daemon could not bind {HOST}:{resolved} — {e}", file=sys.stderr, flush=True)
        return 1

    allowed = folders.roots()
    print(f"zaelar-daemon {VERSION} on http://{HOST}:{resolved}", flush=True)
    print(f"  folders: {', '.join(allowed) if allowed else '(none yet — the engine will ask)'}", flush=True)
    audit.record("daemon.start", outcome="ok", detail={"port": resolved, "roots": len(allowed)})

    thread = threading.Thread(target=server.serve_forever, name="zaelar-daemon", daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nzaelar-daemon stopping…", flush=True)
    finally:
        audit.record("daemon.stop", outcome="ok")
        server.shutdown()
        server.server_close()
    return 0
