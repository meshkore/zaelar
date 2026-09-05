"""Everything that touches the user's disk, and nothing else.

  `refusal`   the exception every module here raises and the HTTP layer catches.
  `roots`     THE PERMISSION CIRCUIT — the one gate; nothing below builds a path from caller input on its own.
  `safeopen`  opening a path the circuit approved, without trusting the disk stayed still in between.
  `entries`   how one file is described, and every budget a read is bounded by.
  `listing` · `reading` · `searching`   the three capabilities, one per file.

READ ONLY. Nothing in this package opens a file for writing; a test asserts that absence by reading the source,
because a write that appeared by accident would pass every other test in the suite — they all only ever read.

⚠️ `roots` THE FUNCTION IS NOT RE-EXPORTED HERE, and that is deliberate rather than an omission. This package has
a submodule called `roots` and that submodule has a function called `roots`; re-exporting the function binds it
over the submodule on the package, so `from daemon.fs import roots` silently hands back a function to code that
wanted the module. It does not fail at import — it fails later, on the first attribute access, in whichever file
happened to write the shorter import. That cost a boot; the shape is `roots.roots()` and the collision is gone.
"""
from __future__ import annotations

from . import entries, listing, reading, refusal, roots, safeopen, searching
from .entries import IMAGE_SUFFIXES, MAX_READ_BYTES, TEXTUAL_SUFFIXES
from .listing import list_dir
from .reading import read_file
from .refusal import Refusal
from .roots import Boundary, candidates, grant, resolve, revoke
from .safeopen import open_read
from .searching import search

__all__ = [
    # submodules, so `from daemon import fs; fs.roots.roots()` reads the way it looks
    "entries", "listing", "reading", "refusal", "roots", "safeopen", "searching",
    # the surface
    "Boundary", "Refusal", "resolve", "grant", "revoke", "candidates", "open_read",
    "list_dir", "read_file", "search",
    "MAX_READ_BYTES", "TEXTUAL_SUFFIXES", "IMAGE_SUFFIXES",
]
