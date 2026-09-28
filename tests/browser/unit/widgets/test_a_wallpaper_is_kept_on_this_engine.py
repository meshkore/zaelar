"""A wallpaper is copied once and served from this engine (demo pass 2026-09-28, full15 B2).

The nebula chosen as backdrop came from a site answering `Cross-Origin-Resource-Policy: same-origin`: the browser
refused it as a background, the desk stayed bare, and the reply said it was set. A backdrop the desk wears all day
now comes from here, not from a third party's hotlink policy."""
import io
import os
import urllib.request

import pytest


class _Resp(io.BytesIO):
    def __init__(self, body, ctype):
        super().__init__(body)
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def props(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from config import settings
    kept = {}
    monkeypatch.setattr(settings, "update", lambda d: kept.update(d))
    monkeypatch.setattr(settings, "wallpaper", lambda: settings._sanitize_wallpaper(kept.get("wallpaper")))
    from widgets import desktop_props
    monkeypatch.setattr(desktop_props, "_emit_wallpaper", lambda *a: None)
    return desktop_props


def test_the_picture_is_fetched_once_and_served_from_here(props, monkeypatch, tmp_path):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(b"\xff\xd8jpeg", "image/jpeg"))
    got = props.set_wallpaper("https://www.wallpaperflare.com/static/nebula.jpg", "Blue nebula")
    assert got["url"].startswith("/widgets/desktop/asset/wallpaper-") and got["url"].endswith(".jpg"), got
    from widgets import store
    assert os.listdir(store.data_dir("desktop")) == [got["url"].rsplit("/", 1)[1]]
    props.set_wallpaper("https://x/second.jpg")
    assert len(os.listdir(store.data_dir("desktop"))) == 1, "one backdrop on disk, never a pile"


def test_a_fetch_that_fails_keeps_the_remote_address(props, monkeypatch):
    def _boom(*a, **k):
        raise OSError("blocked")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert props.set_wallpaper("https://images.example.com/n.jpg")["url"] == "https://images.example.com/n.jpg"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(b"<html>", "text/html"))
    assert props.set_wallpaper("https://images.example.com/m.jpg")["url"] == "https://images.example.com/m.jpg"


def test_only_this_engines_own_copy_passes_as_a_path():
    from config.settings import _sanitize_wallpaper
    assert _sanitize_wallpaper({"url": "/widgets/desktop/asset/wallpaper-ab12.jpg"})["url"]
    assert _sanitize_wallpaper({"url": "/etc/passwd"}) == {}
    assert _sanitize_wallpaper({"url": "/widgets/desktop/asset/a\\\")x"}) == {}
