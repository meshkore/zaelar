"""The text of one allowed file, capped.

READ ONLY. There is no code path in this package that opens a file for writing — creating, editing and deleting
are the irreversible half and live behind their own confirmation, later. A test asserts that ABSENCE by reading
the source, because a write that appeared by accident would pass every other test in the suite: they all only
ever read.
"""
from __future__ import annotations

import os

from .entries import MAX_READ_BYTES
from .refusal import Refusal
from .roots import Boundary
from .safeopen import open_read


def read_file(raw_path: str, *, max_bytes: int = MAX_READ_BYTES) -> dict:
    boundary = Boundary.current()
    target = boundary.check(raw_path)
    if target.is_dir():
        raise Refusal("not_a_file", f"'{target}' is a folder. Ask me to list it instead.")

    cap = max(1, min(int(max_bytes or MAX_READ_BYTES), MAX_READ_BYTES))
    fd = open_read(target, boundary)
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

    return {
        "ok": True,
        "path": str(target),
        "name": target.name,
        "size": int(size),
        "truncated": size > len(raw),
        "text": raw.decode("utf-8", errors="replace"),
    }
