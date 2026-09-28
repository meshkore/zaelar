"""A desktop is landscape: a wallpaper search puts wider-than-tall pictures first (demo pass 2026-09-28, B2).

«find me a deep space wallpaper, like a blue nebula» — none of the six was ≥1600 px wide, so the order was area
alone, and a PHONE wallpaper (800x1422) came first; «set the first one as my background» stretched it across a
1600x1000 desk, blurred and cropped."""
import asyncio


def test_the_landscape_picture_leads_a_wallpaper_search(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.imagenes import data as img
    pics = [{"url": "https://x/phone.jpg", "title": "phone", "w": 800, "h": 1422},
            {"url": "https://x/wide.jpg", "title": "wide", "w": 1280, "h": 720},
            {"url": "https://x/small.jpg", "title": "small", "w": 640, "h": 360}]

    async def images(q, n):
        return {"items": pics, "source": "google"}
    import nucleo.browser_search as bs
    monkeypatch.setattr(bs, "images", images)

    async def brain_action(wid, act, payload):
        return img.apply_action(act, payload)
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    from nucleo.flash import image_turn as it
    parte = asyncio.run(it.execute("blue nebula deep space wallpaper", 6))
    assert parte["ok"] and parte["first"] == "wide", parte
    assert [i["title"] for i in store.load("imagenes", {})["items"]] == ["wide", "small", "phone"]
