"""widgets/desktop_props.py — DESKTOP-level properties a widget may set, owned by the framework (V2-641).

The purity gate is right: a widget's `data.py` is stdlib-only, and the wallpaper action in `imagenes` broke
that by importing `config` directly (caught by the validator the day after it shipped). The boundary that
makes sense is not an exemption — it is this seam: a widget that wants to change something about the DESKTOP
(not about itself) asks the widget framework, and the framework owns the system imports, the sanitizing
store (`config/settings.py`, the CSS-injection seam) and the live push to every open frontend. `imagenes`
imports `widgets.desktop_props`, which the gate already allows for every widget.
"""
from __future__ import annotations


def _emit_wallpaper(url: str, title: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "wallpaper", extra={"id": "imagenes", "url": url, "title": title})
    except Exception:
        pass


def set_wallpaper(url: str, title: str = "") -> dict:
    """Persist + push the desktop wallpaper. Returns the STORED value ({} = the sanitizer refused it) — the
    caller reports against what was actually kept, never against what it asked for."""
    from config import settings as _settings
    _settings.update({"wallpaper": {"url": str(url or ""), "title": str(title or "")}})
    stored = _settings.wallpaper()
    if stored.get("url"):
        _emit_wallpaper(stored["url"], stored.get("title") or "")
    return stored


def clear_wallpaper() -> None:
    from config import settings as _settings
    _settings.update({"wallpaper": None})
    _emit_wallpaper("", "")
