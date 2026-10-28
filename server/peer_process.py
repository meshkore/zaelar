"""server/peer_process.py — which process on this machine sent a request (2026-10-14).

A background worker is a Claude Code (or Codex/Grok) session with Bash, on the operator's own machine. To the
HTTP layer its `curl` looks exactly like his browser: a loopback peer, any headers it likes. What the worker
cannot forge is where its process came from, so the operator's own routes ask that (`server/operator_gate.py`):

  · the peer socket is found among this user's processes (the client end of the connection: its local address is
    the request's peer address, its remote port is the port this engine served it on);
  · that process is a WORKER when the engine is one of its ancestors (a worker, its tools, the agent's own
    Chromium, the widget generator), when it lives in a session a worker opened (`nucleo/workers/providers/spawned.py` —
    this catches an orphan whose parent died), or when it carries a worker's environment markers;
  · the engine itself is SELF; anything else on the machine is OUTSIDE (his browser, his terminal, the harness);
  · a socket nobody here owns is UNKNOWN — another machine, or a connection already gone.

Limits, said plainly: a process that calls `setsid()` itself, after scrubbing its environment and orphaning
itself, is no longer recognisable — that takes deliberate evasion with a language runtime, not a `curl`.
"""
from __future__ import annotations

import ipaddress
import os

SELF, WORKER, OUTSIDE, UNKNOWN = "self", "worker", "outside", "unknown"
WORKER_ENV = ("ZAELAR_WORKER", "ZAELAR_TASK_TOKEN", "ZAELAR_TASK_ID")


def _ip(raw: str):
    try:
        a = ipaddress.ip_address((raw or "").split("%", 1)[0])
    except ValueError:
        return None
    return getattr(a, "ipv4_mapped", None) or a


def _is_client_end(conn, peer, peer_port: int, server_port: int) -> bool:
    la, ra = getattr(conn, "laddr", None), getattr(conn, "raddr", None)
    if not la or not ra or la.port != peer_port or ra.port != server_port:
        return False
    return _ip(la.ip) == peer


def find_pid(peer_ip: str, peer_port: int, server_port: int) -> int | None:
    """The pid owning the client end of this connection, or None."""
    import psutil
    peer = _ip(peer_ip)
    if peer is None or not peer_port or not server_port:
        return None
    try:                                    # Linux/Windows: one call; macOS needs root for it → per-process scan
        conns = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        conns = None                        # the per-process scan below is the macOS road, not a failure
    if conns is not None:
        return next((c.pid for c in conns if c.pid and _is_client_end(c, peer, peer_port, server_port)), None)
    uid = os.getuid() if hasattr(os, "getuid") else None
    for p in psutil.process_iter():
        try:
            if uid is not None and p.uids().real != uid:
                continue
            if any(_is_client_end(c, peer, peer_port, server_port) for c in p.net_connections(kind="tcp")):
                return p.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue                        # macOS: a process closing a socket mid-scan raises ENOTSOCK (2026-10-14)
    return None


def classify(pid: int | None, *, engine_pid: int, worker_sids: frozenset[int]) -> str:
    """SELF / WORKER / OUTSIDE / UNKNOWN for one pid (see the module docstring)."""
    import psutil
    if not pid:
        return UNKNOWN
    if pid == engine_pid:
        return SELF
    try:
        proc = psutil.Process(pid)
        if engine_pid in {a.pid for a in proc.parents()}:
            return WORKER
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return UNKNOWN
    except psutil.AccessDenied:
        return UNKNOWN
    getsid = getattr(os, "getsid", None)
    if getsid is not None:
        try:
            if getsid(pid) in worker_sids:
                return WORKER
        except OSError:
            return UNKNOWN
    try:
        env = proc.environ()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        env = {}                            # unreadable (a platform binary on macOS): no evidence either way
    if any(env.get(k) for k in WORKER_ENV):
        return WORKER
    return OUTSIDE


def kind_of(peer_ip: str, peer_port: int, server_port: int) -> str:
    """Blocking (a process scan, ~15 ms on a busy Mac): call it off the event loop."""
    from nucleo.workers.providers import spawned
    return classify(find_pid(peer_ip, peer_port, server_port), engine_pid=os.getpid(),
                    worker_sids=spawned.sessions())
