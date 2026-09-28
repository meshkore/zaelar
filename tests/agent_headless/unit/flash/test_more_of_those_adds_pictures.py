"""«Show me a few more of those» ADDS pictures; it does not reload the same twelve (demo pass 2026-09-28, I2)."""
import asyncio

import pytest


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.imagenes import data as img
    first = [{"url": f"https://x/{i}.jpg", "thumb": f"https://x/{i}.jpg", "title": f"F40 {i}"} for i in range(12)]
    img.apply_action("show", {"items": first, "query": "red Ferrari F40"})
    deeper = first + [{"url": f"https://x/{i}.jpg", "thumb": f"https://x/{i}.jpg", "title": f"F40 {i}"}
                      for i in range(12, 20)]
    seen = {}

    async def images(q, n):
        seen["n"] = n
        return {"items": deeper[:n], "source": "google"}
    import nucleo.browser_search as bs
    monkeypatch.setattr(bs, "images", images)

    async def brain_action(wid, act, payload):
        return img.apply_action(act, payload)
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    return seen


def test_more_adds_only_new_pictures(viewer):
    from nucleo.flash import image_turn as it
    parte = asyncio.run(it.execute("red Ferrari F40", 8, more=True))
    assert viewer["n"] == 20, "asked deeper than what is already shown"
    assert parte["ok"] and parte["added"] == 8 and parte["count"] == 20
    assert "added 8 more" in it.spoken_for(parte, "Done.") or "añadido 8 más" in it.spoken_for(parte, "Hecho.")


def test_the_tool_offers_it():
    from nucleo.flash import router
    f = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "show_images")
    assert f["parameters"]["properties"]["more"]["type"] == "boolean"
    from nucleo.flash import image_turn as it
    assert it.request_from([{"name": "show_images", "args": {"query": "x", "more": True}}])["more"] is True
