# MEDIA (V2-543) — the files that travel with a message, in both directions.
#
# The WhatsApp bridge has downloaded every image/video/audio/document to disk since day one and pushed the
# absolute paths in `mediaUrls` — this whitelist was the single line where they died (measured 2026-09-01:
# the strings mediaUrls/hasMedia/mediaType appeared in bridge.js and NOWHERE in Python). To be visible, a
# file must live DIRECTLY in the widget's own data dir (`widgets/_data/mensajeria/`): that is the only place
# `GET /widgets/mensajeria/asset/{name}` serves, and its namespace is FLAT (basename-only, path-safe).
import os
import re
import shutil

_MEDIA_MAX_PER_MSG = 6
_MEDIA_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _media_dir() -> str:
    from widgets import store
    return store.data_dir(_svc.WIDGET_ID)


def sendable(paths) -> list[str]:
    """The attachments of a send order that may actually leave: files inside the messaging widget's own data
    dir (uploads and downloads), nothing else. The order came over the bus from the widget, but a send is the
    one thing that takes a file OFF this machine, so the connector checks again where it is."""
    base = os.path.realpath(_media_dir())
    out = []
    for p in paths or []:
        real = os.path.realpath(str(p or ""))
        if os.path.dirname(real) == base and os.path.isfile(real):
            out.append(real)
    return out


_KIND_BY_EXT = {"jpg": "image", "jpeg": "image", "png": "image", "webp": "image", "gif": "image", "heic": "image",
                "mp4": "video", "mov": "video", "mkv": "video", "webm": "video",
                "ogg": "ptt", "opus": "ptt", "mp3": "audio", "m4a": "audio", "wav": "audio", "aac": "audio"}


def kind_of(path: str) -> str:
    """image | video | ptt | audio | document, from the file name — the vocabulary every connector speaks."""
    return _KIND_BY_EXT.get(str(path).rsplit(".", 1)[-1].lower(), "document")


def media_refs(paths) -> list[dict]:
    """The `media` entries of a message WE sent with these files, so the conversation shows what went."""
    out = []
    for p in paths or []:
        out += _media_entries({"mediaUrls": [p], "mediaType": kind_of(p)})
    return out


def _media_entries(m: dict) -> list[dict]:
    """Local media paths → asset URLs the widget can render. A file already inside the widget's data dir is
    referenced in place; one elsewhere (e.g. a legacy ~/.hermes cache from an old bridge process) is COPIED
    in. Best-effort per file: a missing/unreadable file is skipped, never an error — the message must land
    with or without its picture."""
    urls: list[dict] = []
    mtype = str(m.get("mediaType") or "")
    for path in (m.get("mediaUrls") or [])[:_MEDIA_MAX_PER_MSG]:
        try:
            p = str(path or "")
            if not p or not os.path.isfile(p):
                continue
            name = _MEDIA_SAFE.sub("", os.path.basename(p))
            if not name:
                continue
            dest_dir = _media_dir()
            dest = os.path.join(dest_dir, name)
            if os.path.abspath(os.path.dirname(p)) != os.path.abspath(dest_dir):
                if not os.path.isfile(dest):
                    shutil.copy2(p, dest)
            urls.append({"url": f"/widgets/{_svc.WIDGET_ID}/asset/{name}", "type": mtype, "name": name})
        except Exception:
            continue
    return urls


def with_media(m: dict) -> dict:
    """The message with its downloaded files as `media` entries the card can play — for EVERY direction.

    V2-819: the bridge downloads a voice note the operator sends from his phone exactly as it downloads one he
    receives, and hands over the same `mediaUrls`. Only the INBOUND door turned those paths into `media`; the
    outbound one (`record_outbound`) passed them through raw, so his own voice notes reached the thread as a bare
    «audio» label with nothing to play. One function, both doors."""
    if not isinstance(m, dict) or not (m.get("hasMedia") or m.get("mediaUrls")) or m.get("media"):
        return m
    out = dict(m)
    out["mediaType"] = str(m.get("mediaType") or "")
    media = _media_entries(m)
    if media:
        out["media"] = media
    return out


# Read back through the facade (V2-778 F1): one copy of WIDGET_ID.
from connectors.messaging import store as _svc  # noqa: E402
