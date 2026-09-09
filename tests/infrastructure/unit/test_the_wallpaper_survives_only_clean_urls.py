"""The wallpaper URL is echoed into a CSS url("…") on every client (V2-641) — config/settings.py's
sanitizer is therefore a SECURITY seam, exactly like the theme knobs (V2-617): a stored value must never be
able to carry anything but an http(s) address. Anything else collapses to {} — "no wallpaper", never a
partially trusted value."""
from __future__ import annotations

from config.settings import _sanitize_wallpaper


def test_a_clean_url_passes_whole_with_its_title():
    w = _sanitize_wallpaper({"url": "https://images.example.com/canyon.jpg?w=2900&h=1440",
                             "title": "Cañón del Colorado"})
    assert w["url"].endswith("h=1440") and w["title"] == "Cañón del Colorado"


def test_css_breakout_characters_kill_the_whole_value():
    for url in ('https://x.com/a") } body{--x:1',      # closes the url() and opens a rule
                "https://x.com/a'gap",                  # quote variant
                "https://x.com/a\\evil",                # backslash escape
                "https://x.com/<svg>", "https://x.com/a b.jpg", "https://x.com/a\nb"):
        assert _sanitize_wallpaper({"url": url}) == {}, f"{url!r} must be rejected whole"


def test_only_http_s_schemes_exist():
    for url in ("javascript:alert(1)", "data:image/png;base64,AAAA", "file:///etc/passwd", "ftp://x/a.jpg"):
        assert _sanitize_wallpaper({"url": url}) == {}


def test_shapelessness_is_no_wallpaper():
    for raw in (None, "", 42, [], {"title": "sin url"}, {"url": ""}, {"url": "https://x/" + "a" * 3000}):
        assert _sanitize_wallpaper(raw) == {}


def test_the_title_is_bounded_and_optional():
    assert "title" not in _sanitize_wallpaper({"url": "https://x.com/a.jpg"})
    w = _sanitize_wallpaper({"url": "https://x.com/a.jpg", "title": "x" * 500})
    assert len(w["title"]) == 120
