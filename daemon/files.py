"""list · read · search over the folders the user allowed. READ ONLY in v1.

ON DEMAND, WITH NO INDEX (operator's decision 7). Every request walks the real filesystem at the moment it is
asked. That is a deliberate trade and the limit is said out loud rather than discovered: searching inside a lot
of documents is SLOW, and `search()` reports honestly when it stopped early instead of returning a short list
that looks complete. An index would be faster and would also mean a background process reading everything the
user allowed, on its own schedule, into a store the user cannot see — a much bigger thing to ask for than v1
needs.

WRITING IS NOT HERE. Creating, editing and deleting are P5, behind their own confirmation, because they are the
irreversible half. There is no code path in this module that opens a file for writing.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import permissions
from .permissions import Refusal

# A read is capped so one request cannot pull a 2 GB file through the relay. The cap is reported when it bites,
# so "the file was longer than this" is a fact the agent can say rather than a silent truncation it repeats as
# if it were the whole document.
MAX_READ_BYTES = 2 * 1024 * 1024

# Search budgets. Both are reported when hit — see the module docstring: the limit is stated, never hidden.
SEARCH_MAX_FILES = 20_000
SEARCH_MAX_SECONDS = 20.0
SEARCH_MAX_CONTENT_BYTES = 1 * 1024 * 1024      # per file, when searching inside contents

# Extensions worth opening when the caller asks to search inside files. Everything else is matched by name only:
# grepping a 500 MB video for a word is pure cost with no chance of a hit.
TEXTUAL_SUFFIXES = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".html", ".htm", ".xml", ".py", ".js", ".ts", ".css", ".sh", ".sql", ".rtf", ".tex", ".srt", ".vtt",
})

# Extensions the agent can actually show. Not a permission boundary — a hint, so the engine knows which entries
# it can put in a widget without opening them first.
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tiff", ".svg"})


def _entry(p: Path) -> dict:
    """One filesystem entry as the engine sees it. `lstat`, not `stat`: a directory listing should describe what
    is actually there, and reporting a symlink's target size as its own would be a small lie the agent repeats."""
    try:
        st = p.lstat()
    except Exception:           # noqa: BLE001 — vanished between listing and stat: skip it rather than crash
        return {}
    is_link = p.is_symlink()
    try:
        is_dir = p.is_dir()     # follows the link on purpose: "is this browsable?"
    except Exception:           # noqa: BLE001
        is_dir = False
    suffix = p.suffix.lower()
    return {
        "name": p.name,
        "path": str(p),
        "kind": "folder" if is_dir else "file",
        "size": None if is_dir else int(st.st_size),
        "modified": int(st.st_mtime),
        "link": is_link,
        "image": suffix in IMAGE_SUFFIXES,
        "textual": suffix in TEXTUAL_SUFFIXES,
    }


def list_dir(raw_path: str | None = None, *, limit: int = 500) -> dict:
    """The contents of one allowed folder. With no path, the allowlist itself — which is the only sensible
    answer to "what can you see?" and saves the engine from having to know the roots to ask about them."""
    if not raw_path:
        roots = permissions.roots()
        return {
            "ok": True,
            "path": None,
            "roots": roots,
            "entries": [_entry(Path(r)) for r in roots],
            "truncated": False,
        }

    target = permissions.resolve(raw_path)
    if not target.is_dir():
        raise Refusal("not_a_folder", f"'{target}' is a file, not a folder.")

    entries: list[dict] = []
    truncated = False
    try:
        with os.scandir(target) as it:
            for de in it:
                if len(entries) >= limit:
                    truncated = True
                    break
                child = Path(de.path)
                # A symlink out of the allowlist is listed as a link and NOT followed. Silently hiding it would
                # be worse: the user can see it in Finder, so an agent that cannot must be able to say why.
                try:
                    permissions.resolve(str(child), must_exist=False)
                except Refusal:
                    entries.append({"name": de.name, "path": de.path, "kind": "blocked", "size": None,
                                    "modified": None, "link": True, "image": False, "textual": False})
                    continue
                e = _entry(child)
                if e:
                    entries.append(e)
    except PermissionError:
        raise Refusal("not_readable", f"The operating system will not let me open '{target}'.") from None
    except OSError as e:
        raise Refusal("not_readable", f"I could not read '{target}': {e.strerror or e}") from None

    entries.sort(key=lambda e: (e.get("kind") != "folder", (e.get("name") or "").lower()))
    return {"ok": True, "path": str(target), "entries": entries, "truncated": truncated}


def read_file(raw_path: str, *, max_bytes: int = MAX_READ_BYTES) -> dict:
    """The text of one allowed file, capped."""
    target = permissions.resolve(raw_path)
    if target.is_dir():
        raise Refusal("not_a_file", f"'{target}' is a folder. Ask me to list it instead.")

    cap = max(1, min(int(max_bytes or MAX_READ_BYTES), MAX_READ_BYTES))
    fd = permissions.open_read(target)
    try:
        size = os.fstat(fd).st_size
        raw = os.read(fd, cap)
        # `os.read` on a regular file can come back short; loop until we have the cap or the file ends.
        while len(raw) < cap:
            chunk = os.read(fd, cap - len(raw))
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)

    # A NUL byte in the first block is the oldest and still the most reliable binary test. Refusing with the
    # reason named beats handing the agent a page of replacement characters it will try to summarize.
    if b"\x00" in raw[:8192]:
        raise Refusal(
            "binary",
            f"'{target.name}' is not a text file, so there is nothing for me to read out of it directly.",
        )

    text = raw.decode("utf-8", errors="replace")
    return {
        "ok": True,
        "path": str(target),
        "name": target.name,
        "size": int(size),
        "truncated": size > len(raw),
        "text": text,
    }


def search(query: str, *, raw_path: str | None = None, content: bool = False, limit: int = 100) -> dict:
    """Find files by name, and optionally by what is inside them.

    Returns `stopped_early` with the reason whenever a budget was hit, because a search that quietly gave up is
    indistinguishable from a search that found everything — and the agent would report the second."""
    needle = (query or "").strip().lower()
    if not needle:
        raise Refusal("bad_query", "Tell me what to look for.")

    if raw_path:
        scope = [permissions.resolve(raw_path)]
        if not scope[0].is_dir():
            raise Refusal("not_a_folder", f"'{scope[0]}' is a file, not a folder to search in.")
    else:
        scope = [Path(r) for r in permissions.roots()]
    if not scope:
        raise Refusal("no_folders", "You have not given me access to any folder yet.", folders=[])

    hits: list[dict] = []
    scanned = 0
    started = time.monotonic()
    stopped_early: str | None = None

    for root in scope:
        if stopped_early:
            break
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if stopped_early:
                break
            here = Path(dirpath)
            # Prune whole subtrees the allowlist would refuse anyway (a sensitive name, a link out). Pruning
            # rather than filtering at the leaf is what keeps `~/Library` from costing a minute per search.
            keep = []
            for d in dirnames:
                try:
                    permissions.resolve(str(here / d), must_exist=False)
                    keep.append(d)
                except Refusal:
                    continue
            dirnames[:] = keep

            for fname in filenames:
                scanned += 1
                if scanned > SEARCH_MAX_FILES:
                    stopped_early = "too_many_files"
                    break
                if time.monotonic() - started > SEARCH_MAX_SECONDS:
                    stopped_early = "timeout"
                    break
                fpath = here / fname
                try:
                    target = permissions.resolve(str(fpath))
                except Refusal:
                    continue

                where = None
                if needle in fname.lower():
                    where = "name"
                elif content and target.suffix.lower() in TEXTUAL_SUFFIXES:
                    if _contains(target, needle):
                        where = "content"
                if not where:
                    continue

                e = _entry(target)
                if e:
                    e["matched"] = where
                    hits.append(e)
                if len(hits) >= limit:
                    stopped_early = "limit"
                    break

    return {
        "ok": True,
        "query": query,
        "scope": [str(p) for p in scope],
        "content_searched": bool(content),
        "hits": hits,
        "scanned": scanned,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "stopped_early": stopped_early,
    }


def _contains(target: Path, needle: str) -> bool:
    """Is `needle` in the first megabyte of this file? Best-effort by design: a file that cannot be opened is
    not a match and not an error, because one unreadable file must not fail a search over ten thousand."""
    try:
        fd = permissions.open_read(target)
    except Refusal:
        return False
    try:
        raw = os.read(fd, SEARCH_MAX_CONTENT_BYTES)
    except Exception:           # noqa: BLE001
        return False
    finally:
        os.close(fd)
    if b"\x00" in raw[:8192]:
        return False
    return needle in raw.decode("utf-8", errors="ignore").lower()
