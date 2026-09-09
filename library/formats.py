"""What kind of thing a file is, and whether THIS browser can play it (V2-638).

The operator's rule, and the reason this module exists: **by default the agent only brings home what it can
actually play** — fetching a 12 GB container the `<video>` tag refuses is a download that ends in an apology.
The escape hatch is explicit and narrow: when he says he wants the file itself (to copy onto a pendrive, to
open elsewhere), `keep` lifts the policy and any format is allowed. So the policy is a DEFAULT, never a wall.

This corrects a real defect in the first cut of the torrent client (V2-637): `.mkv` and `.avi` were in its
"playable video" list. They are not — Chrome, Safari and Firefox all refuse `.mkv` and `.avi` regardless of
what is inside them, so the add-on could have picked a file it was structurally unable to show. The lists
below are the codecs/containers a mainstream browser actually decodes, not the ones a media player does.
"""
from __future__ import annotations

import os

# Containers a mainstream browser decodes natively. Deliberately CONSERVATIVE: a format that plays in some
# browsers and not others is worse than one we file as "download only", because the failure lands on the
# operator as a black rectangle with no explanation.
VIDEO = (".mp4", ".m4v", ".webm", ".ogv", ".mov")
AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac")
IMAGE = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".bmp")
DOCUMENT = (".pdf", ".txt", ".md", ".html", ".htm")

# Known-but-unplayable: recognized as MEDIA (so we can name what it is and offer to keep it) while never
# being chosen for playback. Anything not listed anywhere is simply "other".
VIDEO_UNPLAYABLE = (".mkv", ".avi", ".wmv", ".flv", ".ts", ".m2ts", ".mpg", ".mpeg", ".rmvb", ".divx")
AUDIO_UNPLAYABLE = (".wma", ".ape", ".aiff", ".alac", ".mid", ".midi")
DOCUMENT_OTHER = (".epub", ".mobi", ".azw3", ".djvu", ".doc", ".docx", ".odt", ".rtf")

_MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg",
    ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
    ".oga": "audio/ogg", ".opus": "audio/opus", ".wav": "audio/wav", ".flac": "audio/flac",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif", ".svg": "image/svg+xml", ".bmp": "image/bmp",
    ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown", ".html": "text/html",
    ".htm": "text/html", ".epub": "application/epub+zip",
}


def ext_of(name: str) -> str:
    return os.path.splitext(str(name or ""))[1].lower()


def kind_of(name: str) -> str:
    """`video` | `audio` | `image` | `document` | `other` — what SHELF this belongs on, playable or not.

    Kind and playability are separate questions on purpose: an `.mkv` is still a video (it belongs in
    video/, it can be offered as a download), it just cannot be played in the page."""
    e = ext_of(name)
    if e in VIDEO or e in VIDEO_UNPLAYABLE:
        return "video"
    if e in AUDIO or e in AUDIO_UNPLAYABLE:
        return "audio"
    if e in IMAGE:
        return "image"
    if e in DOCUMENT or e in DOCUMENT_OTHER:
        return "document"
    return "other"


def browser_playable(name: str) -> bool:
    """Can the page itself render/play this, with no external app? (`<video>`, `<audio>`, `<img>`, the PDF
    viewer.) This is the question the default policy is built on."""
    e = ext_of(name)
    return e in VIDEO or e in AUDIO or e in IMAGE or e in DOCUMENT


def mime_of(name: str) -> str:
    return _MIME.get(ext_of(name), "application/octet-stream")


def allowed(name: str, *, keep: bool = False) -> bool:
    """May the agent bring this file home? Playable → always. Anything else → only when the operator has
    explicitly asked to KEEP the file (his pendrive case), never as a silent default."""
    return True if keep else browser_playable(name)


def refusal(name: str) -> str:
    """Why a file was not taken — said so the operator can overrule it in the same breath."""
    e = ext_of(name) or "sin extensión"
    return (f"«{os.path.basename(str(name or ''))}» es un {e} y el navegador no lo reproduce; "
            "dime que lo quieras guardar igualmente y te lo descargo para llevártelo.")
