"""list · read · search, kept at their old address.

The three capabilities moved into `daemon.fs` (one module each) when the daemon was split. This module stays
because it is the name the engine and the tests already say.

⚠️ The absence of a write path is asserted over the whole `daemon/fs` package, not over this file. A shim has no
write path by construction, so a test that kept reading THIS source would have gone on passing while the real
code grew one — a green light on the exact thing it was watching.
"""
from __future__ import annotations

from .fs.entries import (
    IMAGE_SUFFIXES,
    MAX_READ_BYTES,
    SEARCH_MAX_CONTENT_BYTES,
    SEARCH_MAX_FILES,
    SEARCH_MAX_SECONDS,
    TEXTUAL_SUFFIXES,
)
from .fs.listing import list_dir
from .fs.reading import read_file
from .fs.searching import search

__all__ = [
    "list_dir", "read_file", "search",
    "MAX_READ_BYTES", "SEARCH_MAX_FILES", "SEARCH_MAX_SECONDS", "SEARCH_MAX_CONTENT_BYTES",
    "TEXTUAL_SUFFIXES", "IMAGE_SUFFIXES",
]
