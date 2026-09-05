"""Find files by name, and optionally by what is inside them.

ON DEMAND, WITH NO INDEX. Every request walks the real filesystem at the moment it is asked. That is a
deliberate trade and the limit is said out loud rather than discovered: searching inside a lot of documents is
SLOW, and this reports honestly when it stopped early instead of returning a short list that looks complete. An
index would be faster and would also mean a background process reading everything the user allowed, on its own
schedule, into a store the user cannot see — a much bigger thing to ask for than this needs.

`stopped_early` carries the REASON, because a search that quietly gave up is indistinguishable from a search
that found everything, and the agent would report the second.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .entries import (
    SEARCH_MAX_CONTENT_BYTES,
    SEARCH_MAX_FILES,
    SEARCH_MAX_SECONDS,
    TEXTUAL_SUFFIXES,
    describe,
)
from .refusal import Refusal
from .roots import Boundary
from .safeopen import open_read

SEARCH_MAX_LIMIT = 1_000


def _contains(target: Path, needle: str, boundary: Boundary) -> bool:
    """Is `needle` in the first megabyte of this file? Best-effort by design: a file that cannot be opened is
    not a match and not an error, because one unreadable file must not fail a search over ten thousand."""
    try:
        fd = open_read(target, boundary)
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


def search(query: str, *, raw_path: str | None = None, content: bool = False, limit: int = 100) -> dict:
    needle = (query or "").strip().lower()
    if not needle:
        raise Refusal("bad_query", "Tell me what to look for.")
    limit = max(1, min(int(limit or 100), SEARCH_MAX_LIMIT))

    boundary = Boundary.current()
    if raw_path:
        scope = [boundary.check(raw_path)]
        if not scope[0].is_dir():
            raise Refusal("not_a_folder", f"'{scope[0]}' is a file, not a folder to search in.")
    else:
        scope = list(boundary.roots)
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
            # Prune whole subtrees the boundary would refuse anyway (a denied name, a link out). Pruning rather
            # than filtering at the leaf is what keeps a granted home directory from costing a minute a search.
            keep = []
            for name in dirnames:
                try:
                    boundary.check(str(here / name), must_exist=False)
                    keep.append(name)
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
                try:
                    target = boundary.check(str(here / fname))
                except Refusal:
                    continue

                where = None
                if needle in fname.lower():
                    where = "name"
                elif content and target.suffix.lower() in TEXTUAL_SUFFIXES:
                    if _contains(target, needle, boundary):
                        where = "content"
                if not where:
                    continue

                described = describe(target)
                if described:
                    described["matched"] = where
                    hits.append(described)
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
