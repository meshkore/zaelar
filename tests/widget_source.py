"""A widget's client code as one text, for the guards that READ it (refactor2710-12 T-03).

A large `widget.js` splits into `js/` modules; a guard that read `widgets/<id>/widget.js` alone would go blind to
whatever moved. Read it through here: the entry, then its `js/` modules, joined — the same list the catalog gate
scans (`widgets.paths.client_files`).
"""
from __future__ import annotations

from pathlib import Path

from widgets import paths

ENGINE = Path(__file__).resolve().parents[1]


def client(widget_id: str) -> str:
    return paths.client_source(str(ENGINE / "widgets" / widget_id))
