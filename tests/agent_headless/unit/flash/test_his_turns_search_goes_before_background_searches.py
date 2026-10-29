"""HIS turn's search goes before background searches in the one browser (V2-831 pass 10, I1 on v3.107).

«show me a red ferari f40»: the empty viewer was up at +2.7 s and the words came at +18.7 s — the turn's Google image
search took ~15 s in the single Chromium while an errand's searches (13.9 s, 31.9 s) ran through the same browser on a
1-vCPU host. A search his turn makes holds `browser.foreground()`; the thread bridges every background search goes
through (`search_sync` / `images_sync`) wait while one is in flight, bounded by the declared `browser_bg_wait_s`.
"""
from __future__ import annotations

import asyncio
import threading
import time

from search import browser as B


def test_a_background_search_waits_for_his_and_goes_as_soon_as_it_ends(monkeypatch):
    from search import hooks
    monkeypatch.setattr(hooks, "policy", lambda: {"browser_bg_wait_s": 5})
    waited = []
    with B.foreground():
        t = threading.Thread(target=lambda: waited.append(B._yield_to_his_turn()))
        t.start()
        time.sleep(0.3)
        assert t.is_alive(), "the background search went while his was in flight"
    t.join(2)
    assert waited and 0.25 <= waited[0] < 2.0, waited


def test_the_wait_is_bounded_by_a_declared_clock(monkeypatch):
    from search import hooks
    monkeypatch.setattr(hooks, "policy", lambda: {"browser_bg_wait_s": 0.2})
    with B.foreground():
        assert B._yield_to_his_turn() < 1.0
    assert B._yield_to_his_turn() < 0.05, "nothing in flight: no wait"


def test_the_turns_picture_search_holds_the_foreground(monkeypatch):
    seen = {}

    async def images(q, k):
        seen["fg"] = B._fg["n"]
        return {"items": []}
    monkeypatch.setattr(B, "images", images)
    from nucleo.flash import image_turn
    asyncio.run(image_turn.execute("red ferrari f40"))
    assert seen["fg"] == 1 and B._fg["n"] == 0


def test_the_background_bridges_yield_and_the_bound_is_declared():
    import inspect, json
    from pathlib import Path
    from server.boot import surfaces
    assert "_search_hooks.policy = _envelope.policy" in inspect.getsource(surfaces)
    d = json.loads((Path(B.__file__).resolve().parents[1] / "config" / "resources.default.json").read_text())
    assert "browser_bg_wait_s" in d
    assert "_yield_to_his_turn()" in inspect.getsource(B.search_sync)
    assert "_yield_to_his_turn()" in inspect.getsource(B.images_sync)
