#
# files/store.py — COMPATIBILITY SHIM (V2-003 · T55). The `files/` module is folded into central memory:
# the old flat files/uploads/ inbox and its index are absorbed by the EPISODIC layer of `memory/` (bytes in the
# memory data directory plus an embedded searchable summary; the brain's retriever finds them on its own,
# without an absolute path or Hermes file tools — the [SYSTEM] path note was removed in this change).
#
# This shim is kept ONLY to avoid breaking external importers; it delegates to memory.api. Migration of already
# uploaded files (files/uploads/*) is performed by `memory.migrate_inbox()` at startup (lazy, idempotent, NON-destructive).
#
from memory import api as _memapi


def save_upload(filename: str, data: bytes) -> str:
    """Compat: save to episodic memory and return the path of the stored binary."""
    ref = _memapi.write_episode(data, filename=filename)
    return ref["path"]


def list_files() -> list[dict]:
    """Compat: flat listing derived from memory episodes (name/size/mtime≈created)."""
    return [
        {"name": e["name"], "size": e.get("bytes"), "mtime": e.get("created")}
        for e in _memapi.list_episodes()
    ]
