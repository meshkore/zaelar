"""The HTTP surface, kept at its old address.

The server was split into `daemon.http` (plumbing · routes · lifecycle) and `daemon.security` (the admission
decision, as a pure function over headers) when the daemon was modularized. This module stays because it is the
name the engine, the CLI and the tests already say.

Read `daemon/security/guards.py` for why loopback is not a boundary and what the five guards are.
"""
from __future__ import annotations

from .http.handler import PUBLIC_PATHS as _PUBLIC
from .http.handler import Handler
from .http.lifecycle import build, is_running, resolve_port, serve
from .http.routes import CAPABILITIES
from .http.routes import TABLE as _ROUTES

__all__ = ["Handler", "build", "serve", "is_running", "resolve_port", "CAPABILITIES", "_ROUTES", "_PUBLIC"]
