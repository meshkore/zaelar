"""Everything that decides WHETHER, as opposed to everything that decides WHAT.

Three separate questions live here, and keeping them apart is the point:

  `denylist`  — which NAMES are never served, at any depth, even inside a folder the user granted.
  `guards`    — whether an HTTP request may be served at all (a PURE decision over headers, no sockets).
  `throttle`  — what happens when a caller keeps being refused, so a flood cannot drown the audit log.

None of them touches the filesystem or the network. That is deliberate: a security decision that needs a live
server to exercise is a security decision nobody tests in both directions.
"""
from __future__ import annotations

from . import denylist, guards, throttle

__all__ = ["denylist", "guards", "throttle"]
