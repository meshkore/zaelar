"""The daemon's HTTP surface: standard library, loopback, token-authenticated.

  `handler`    read a request, decide whether to serve it, write a JSON answer.
  `routes`     the route table and one small function per route.
  `lifecycle`  binding, serving, stopping.

The admission decision itself is NOT here — it lives in `daemon.security.guards` as a pure function over
headers, so it can be exercised in both directions without a socket. What is here is the plumbing that calls it
and the guarantee that every refusal looks the same from outside.
"""
from __future__ import annotations

from .handler import PUBLIC_PATHS, Handler
from .lifecycle import build, is_running, resolve_port, serve
from .routes import CAPABILITIES, TABLE

__all__ = ["Handler", "PUBLIC_PATHS", "TABLE", "CAPABILITIES", "build", "serve", "is_running", "resolve_port"]
