"""Opening a file the boundary already approved, WITHOUT trusting that the disk stayed still in between.

THE GAP THIS EXISTS FOR. `Boundary.check()` resolves a path and proves it is inside an allowed folder. Then it
returns, and the caller opens it. Between those two moments the filesystem is not frozen: anything running as
this user can replace the last component with a symlink, or swap a directory halfway up for one that points
somewhere else. The check was true when it was made and false when it was used. That is a TOCTOU race, and on a
daemon whose whole job is "only these folders" it is the way out of them.

THREE CHECKS, and each one closes a different half:

  `O_NOFOLLOW` on the open. `check()` returned a path with no symlinks left in it, so if the FINAL component is
  a link now, something changed in the window — which is exactly the moment to refuse rather than follow it.

  `S_ISREG` on the opened descriptor. A named pipe inside a granted folder is not an attack, it is a Tuesday,
  and `os.read` on one blocks until somebody writes — forever, on a thread that is never coming back. Devices
  and sockets are the same shape of problem. The open uses `O_NONBLOCK` so it cannot hang before we get far
  enough to look, then clears it, because a regular file ignores it and a caller reading one should not have to
  cope with a short read that means "not ready".

  THE DESCRIPTOR'S OWN PATH, re-checked against the boundary. This is the one that catches the swap of a
  directory in the MIDDLE of the path, which the other two cannot see: `O_NOFOLLOW` only looks at the last
  component, and comparing inodes only proves the name and the file still agree with each other, not that
  either is still where it was. The kernel knows where an open descriptor really points — `F_GETPATH` on macOS,
  `/proc/self/fd/N` on Linux — so we ask it, and refuse if the answer landed outside the folders the user
  allowed.

WINDOWS IS A STATED LIMIT, NOT A SOLVED PROBLEM. It has no `O_NOFOLLOW` and no cheap equivalent of
`F_GETPATH`, so the flags degrade to nothing and the third check is skipped. What remains there is the
resolution in `Boundary.check()` plus `S_ISREG`, which is the same protection the daemon had everywhere before
this module existed. Saying so in the docstring is the point: a limit somebody can read is a limit somebody can
close later.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from .refusal import Refusal

# `F_GETPATH` is a Darwin fcntl and Python does not name it. 50 is the value from `<sys/fcntl.h>`; the buffer
# has to be at least MAXPATHLEN (1024) or the call fails with EINVAL.
_F_GETPATH = 50
_MAXPATHLEN = 1024

# `os.O_NOFOLLOW` reports ELOOP on Linux and on macOS; the numbers differ between them, so both are named
# rather than assuming the platform's.
_ELOOP_ERRNOS = {getattr(os, "ELOOP", 62), 62, 40}


def real_path_of(fd: int) -> Path | None:
    """Where this descriptor REALLY points, according to the kernel. None when the platform will not say."""
    try:
        if sys.platform == "darwin":
            import fcntl
            raw = fcntl.fcntl(fd, _F_GETPATH, b"\0" * _MAXPATHLEN)
            return Path(os.fsdecode(raw.split(b"\0", 1)[0]))
        if sys.platform.startswith("linux"):
            return Path(os.readlink(f"/proc/self/fd/{fd}"))
    except Exception:           # noqa: BLE001 — an unavailable answer is not a wrong answer
        return None
    return None


def open_read(target: Path, boundary=None) -> int:
    """Open an ALREADY-RESOLVED path for reading, or raise `Refusal`. The caller owns the descriptor.

    `boundary` is the same `Boundary` the path was checked against. Passing it enables the third check; leaving
    it out keeps the first two, which is what a caller with no boundary in hand (there are none today) would
    get."""
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    try:
        fd = os.open(target, flags)
    except OSError as e:
        if e.errno in _ELOOP_ERRNOS:
            raise Refusal(
                "symlink_race",
                f"'{target}' turned into a link while I was opening it. I stopped rather than follow it.",
            ) from None
        raise Refusal("not_readable", f"I could not open '{target}': {e.strerror or e}") from None

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Refusal(
                "not_a_file",
                f"'{target.name}' is not an ordinary file (it is a pipe, a device or a socket), so there is "
                f"nothing in it for me to read.",
            )

        actual = real_path_of(fd)
        if actual is not None and boundary is not None:
            resolved = actual.resolve()
            if not boundary.contains(resolved) or resolved != target:
                raise Refusal(
                    "path_changed",
                    f"'{target}' moved while I was opening it and the file I ended up with is somewhere else. "
                    f"I stopped rather than read it.",
                )

        # A regular file ignores O_NONBLOCK, but leaving it set means any future caller of this descriptor has
        # to think about EAGAIN. It was only ever there so the open itself could not hang.
        if hasattr(os, "O_NONBLOCK"):
            import fcntl
            fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
    except Exception:
        os.close(fd)
        raise
    return fd
