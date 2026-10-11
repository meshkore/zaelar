"""A settled turn brief with the given sure verdicts — the shape `turn_brief.read` consumes."""
from __future__ import annotations

import threading


def brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


def viewer_on_screen(monkeypatch, *, items: bool = True):
    """The photo viewer open on the canvas, with (or without) the earlier search's pictures in it."""
    from memory import api as memory
    from widgets.imagenes import data as img
    monkeypatch.setattr(memory, "state", lambda: {"open_widgets": ["imagenes"]})
    monkeypatch.setattr(img, "view_data", lambda q="": {"items": [{"url": "https://x.example/a.jpg"}] if items else []})
