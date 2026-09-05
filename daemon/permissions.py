"""The permission circuit, kept at its old address.

The circuit itself moved to `daemon.fs` when the daemon was split into `security` / `fs` / `http`. This module
stays because it is the name the engine, the CLI and the tests already say — a re-export shim, the same shape
the engine uses whenever a piece moves and its callers should not have to care.

Read `daemon/fs/roots.py` for the rules and why they are in that order.
"""
from __future__ import annotations

from .fs.refusal import Refusal
from .fs.roots import Boundary, candidates, grant, resolve, revoke, roots
from .fs.safeopen import open_read

__all__ = ["Refusal", "Boundary", "roots", "resolve", "grant", "revoke", "candidates", "open_read"]
