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


#: Where a wallpaper is kept once copied: the framework's own asset namespace, not `imagenes`' — that widget lists
#: every picture in its directory as «on this computer», and the desktop's backdrop is not one of his photos.
WALL_NS = "desktop"
_WALL_MAX = 15 * 1024 * 1024


_WALL_UA = "Mozilla/5.0 (Zaelar wallpaper)"


def fetchable(url: str, timeout: float = 2.5) -> bool:
    """Whether `_local_copy` could fetch this picture: an image answer to the SAME request it makes. Read by a
    wallpaper search to put the pictures that can become a backdrop first (demo pass 2026-09-28, full17 B2: the
    first nebula came from a site that answers 403 to anything but its own pages, and «set the first one» left the
    desk bare while the reply said it was set). Reads one byte, never the file."""
    import urllib.request
    if not str(url or "").startswith(("http://", "https://")):
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _WALL_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:            # noqa: S310 — http(s) checked above
            ctype = str(r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            r.read(1)
            return ctype in ("image/jpeg", "image/png", "image/webp")
    except Exception:  # noqa: BLE001
        return False


def _local_copy(url: str, timeout: float = 5.0) -> str:
    """The wallpaper served from THIS engine's origin, or "" when it cannot be fetched.

    Demo pass 2026-09-28 (full15 B2): the chosen nebula came from a site that answers with
    `Cross-Origin-Resource-Policy: same-origin` — the browser refused it as a background and the desk stayed
    bare, while the reply said it was set. The viewer had fallen back to the thumbnail without anyone noticing.
    A backdrop the desk wears all day should not depend on a third party's hotlink policy at all: fetch it once,
    keep it, serve it from here. Bounded (size, time, image types only); any failure keeps the remote URL."""
    import hashlib
    import os
    import urllib.request
    if not str(url or "").startswith(("http://", "https://")):
        return ""
    try:
        from widgets import store
        req = urllib.request.Request(url, headers={"User-Agent": _WALL_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:            # noqa: S310 — http(s) checked above
            ctype = str(r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ctype)
            if not ext:
                return ""
            body = r.read(_WALL_MAX + 1)
        if not body or len(body) > _WALL_MAX:
            return ""
        d = store.data_dir(WALL_NS)
        os.makedirs(d, exist_ok=True)
        name = "wallpaper-" + hashlib.sha1(body).hexdigest()[:16] + ext
        with open(os.path.join(d, name), "wb") as fh:
            fh.write(body)
        for old in os.listdir(d):                   # one backdrop on disk, never a growing pile of them
            if old.startswith("wallpaper-") and old != name:
                try:
                    os.remove(os.path.join(d, old))
                except OSError:
                    pass
        return f"/widgets/{WALL_NS}/asset/{name}"
    except Exception:  # noqa: BLE001 — the remote URL is still a wallpaper when the copy fails
        return ""


def set_wallpaper(url: str, title: str = "") -> dict:
    """Persist + push the desktop wallpaper. Returns the STORED value ({} = the sanitizer refused it) — the
    caller reports against what was actually kept, never against what it asked for."""
    from config import settings as _settings
    local = _local_copy(str(url or ""))
    url = local or str(url or "")
    _settings.update({"wallpaper": {"url": str(url or ""), "title": str(title or "")}})
    stored = _settings.wallpaper()
    if stored.get("url"):
        _emit_wallpaper(stored["url"], stored.get("title") or "")
    # `copied` false = the desk now depends on that site letting the browser show it, which is exactly what failed
    # before; the caller says so instead of announcing a backdrop nobody may see.
    return {**stored, "copied": bool(local)} if stored.get("url") else stored


def clear_wallpaper() -> bool:
    """Take the wallpaper off. Returns whether there was one — clearing NOTHING writes nothing and pushes
    nothing: a store write for a no-op is how a unit test that merely calls every declared action ends up
    touching the operator's real settings file (caught by `test_suite_isolation` the day this shipped)."""
    from config import settings as _settings
    if not _settings.wallpaper().get("url"):
        return False
    _settings.update({"wallpaper": None})
    _emit_wallpaper("", "")
    return True
