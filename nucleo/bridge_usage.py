"""nucleo/bridge_usage.py — a bridge's argument error says what to DO, not just what the shape is.

V2-212 taught this on `nav_cli type_at`: argparse prints the FORM (`usage: … x y text`) and the parser's own
complaint (`invalid int value: 'Hotel Palacio…'`), and neither tells a headless worker how to get out. It burns
the turn. That is the same dead end four bridges paid for on 2026-08-20 — a message that says WHAT failed and
nothing about WHAT NOW.

The MECHANISM is shared here because a second copy of it is a copy that drifts (V2-153). The KNOWLEDGE is not:
each bridge passes its own `hint_for(prog)`, because what to do about a bad `scroll` has nothing to do with what
to do about a bad `ask`.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable


def guided(hint_for: Callable[[str], str]) -> type[argparse.ArgumentParser]:
    """An ArgumentParser class whose `error()` adds `hint_for(self.prog)` between the complaint and the usage.

    The hint goes in the MIDDLE on purpose: a worker reads top-down, so the way out has to arrive before the
    wall of syntax it is already staring at.
    """

    class _GuidedParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write(f"{self.prog}: error: {message}\n")
            hint = hint_for(self.prog) or ""
            if hint:
                sys.stderr.write(hint + "\n")
            sys.stderr.write(self.format_usage())
            raise SystemExit(2)

    return _GuidedParser
