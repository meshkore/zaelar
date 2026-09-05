"""`python -m daemon` — start the Zaelar Local Daemon, or run one of its sub-commands.

Kept to the entry point alone so there is exactly one place the process begins. The commands themselves live in
`daemon.cli`, which is importable and therefore testable without spawning a process.
"""
from __future__ import annotations

import sys

from .cli import USAGE, main

__all__ = ["main", "USAGE"]

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
