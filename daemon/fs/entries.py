"""One filesystem entry, as the engine sees it — and the budgets every read is bounded by.

Shared by listing and searching so the two describe the same file the same way. A directory listing and a
search hit that disagree about whether something is an image is a small lie the agent repeats.
"""
from __future__ import annotations

from pathlib import Path

# A read is capped so one request cannot pull a 2 GB file through the relay. The cap is REPORTED when it bites,
# so "the file was longer than this" is a fact the agent can state rather than a silent truncation it repeats as
# if it were the whole document.
MAX_READ_BYTES = 2 * 1024 * 1024

# Search budgets. All three are reported when hit — the limit is stated, never hidden.
SEARCH_MAX_FILES = 20_000
SEARCH_MAX_SECONDS = 20.0
SEARCH_MAX_CONTENT_BYTES = 1 * 1024 * 1024      # per file, when searching inside contents

# How many entries a single listing may return before it says it truncated.
LIST_DEFAULT_LIMIT = 500
LIST_MAX_LIMIT = 5_000

# Extensions worth opening when the caller asks to search inside files. Everything else is matched by name only:
# grepping a 500 MB video for a word is pure cost with no chance of a hit.
TEXTUAL_SUFFIXES = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".html", ".htm", ".xml", ".py", ".js", ".ts", ".css", ".sh", ".sql", ".rtf", ".tex", ".srt", ".vtt",
})

# Extensions the agent can actually show. Not a permission boundary — a hint, so the engine knows which entries
# it can put in a widget without opening them first.
IMAGE_SUFFIXES = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tiff", ".svg",
})


def describe(path: Path) -> dict:
    """`lstat`, not `stat`: a directory listing should describe what is actually there, and reporting a
    symlink's target size as its own would be a small lie the agent repeats."""
    try:
        info = path.lstat()
    except Exception:           # noqa: BLE001 — vanished between listing and stat: skip it rather than crash
        return {}
    is_link = path.is_symlink()
    try:
        is_dir = path.is_dir()  # follows the link on purpose: "is this browsable?"
    except Exception:           # noqa: BLE001
        is_dir = False
    suffix = path.suffix.lower()
    return {
        "name": path.name,
        "path": str(path),
        "kind": "folder" if is_dir else "file",
        "size": None if is_dir else int(info.st_size),
        "modified": int(info.st_mtime),
        "link": is_link,
        "image": suffix in IMAGE_SUFFIXES,
        "textual": suffix in TEXTUAL_SUFFIXES,
    }


def blocked(name: str, path: str) -> dict:
    """An entry the boundary refuses. Listed rather than hidden: the user can see it in Finder, so an agent that
    cannot must be able to say why — silently omitting it makes the file look missing."""
    return {"name": name, "path": path, "kind": "blocked", "size": None, "modified": None,
            "link": True, "image": False, "textual": False}
