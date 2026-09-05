"""What is in one allowed folder.

The boundary is built ONCE and asked about every entry. That is not a micro-optimization: the previous shape
re-read the config and re-resolved every allowed root for each of the thousands of names in a directory, which
turned a permission check into a per-entry filesystem storm and made a large folder feel like a hang.
"""
from __future__ import annotations

import os
from pathlib import Path

from .entries import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, blocked, describe
from .refusal import Refusal
from .roots import Boundary


def list_dir(raw_path: str | None = None, *, limit: int = LIST_DEFAULT_LIMIT) -> dict:
    """The contents of one allowed folder. With no path, the allowlist ITSELF — which is the only sensible
    answer to "what can you see?" and saves the engine from having to know the roots in order to ask about
    them."""
    boundary = Boundary.current()
    limit = max(1, min(int(limit or LIST_DEFAULT_LIMIT), LIST_MAX_LIMIT))

    if not raw_path:
        names = boundary.as_strings()
        return {
            "ok": True,
            "path": None,
            "roots": names,
            "entries": [describe(Path(r)) for r in names],
            "truncated": False,
        }

    target = boundary.check(raw_path)
    if not target.is_dir():
        raise Refusal("not_a_folder", f"'{target}' is a file, not a folder.")

    entries: list[dict] = []
    truncated = False
    try:
        with os.scandir(target) as scan:
            for item in scan:
                if len(entries) >= limit:
                    truncated = True
                    break
                child = Path(item.path)
                # A link out of the allowlist is listed as blocked and NOT followed.
                try:
                    boundary.check(str(child), must_exist=False)
                except Refusal:
                    entries.append(blocked(item.name, item.path))
                    continue
                described = describe(child)
                if described:
                    entries.append(described)
    except PermissionError:
        raise Refusal("not_readable", f"The operating system will not let me open '{target}'.") from None
    except OSError as e:
        raise Refusal("not_readable", f"I could not read '{target}': {e.strerror or e}") from None

    entries.sort(key=lambda e: (e.get("kind") != "folder", (e.get("name") or "").lower()))
    return {"ok": True, "path": str(target), "entries": entries, "truncated": truncated}
