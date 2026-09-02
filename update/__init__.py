"""update/ — THE UPDATE CHANNEL. One number a person can compare, and one honest answer to
«does this browser have to reload?».

It is a package of its own, next to `version.py` and imported by nobody in the agent's hot paths, because
that is the whole design constraint the operator set: «que no ensucie el código actual del agente… que sea
un componente de librería o módulo que se encargue de gestionar las versiones y la actualización». The
engine reaches it in exactly two places — `server/__init__.py` mounts its router, and the Dockerfile ships
it. Nothing in `nucleo/`, `voice/`, `memory/` or `widgets/` knows it exists.

WHAT IT PUBLISHES, and why each field is the shape it is:

  · `build` — a plain incrementing INTEGER, and the only version a user is ever shown. `version.VERSION`
    ("3.16") already exists and is not a substitute: it is semantic, it is bumped by hand for notable
    blocks, and it does not answer «am I newer than my colleague?» at a glance. This one does: 24 is one
    update after 23. It lives in a text FILE (`update/BUILD`) rather than being derived from git, because
    the cloud image has no repository at all — `.git` is not COPYed, so `version.sha()` returns "nogit"
    inside every Machine. A file is the only source of truth that survives to production intact.

  · `ui_rev` — a digest of the bytes THE BROWSER EXECUTES (`frontend/**` with a browser-fetchable
    extension). This is the field that decides whether a reload is worth asking for. The operator was
    explicit: «obviamente en el caso de que los cambios requieran un reinicio del frontend; si solo se ha
    tocado algo del backend obviamente no hace falta». A build number cannot tell those apart — every
    release moves it — so the question is answered by measuring, not by guessing.

    It hashes CONTENT, never mtimes: `COPY` in a Docker build and a fresh `git clone` both invent
    timestamps, so an mtime digest would report a phantom update on every deployment and, worse, would
    fail to report a real one when a file was restored with an old timestamp. 74 files / ~2 MB today,
    hashed ONCE per process on first request and cached — a few milliseconds, never repeated.

    Any failure returns the sentinel `"unknown"`, and clients must treat that as «I cannot tell», never as
    a change: a digest that varies because a read failed halfway would nag forever with a reload that
    fixes nothing.

The browser learns its OWN revision by taking the FIRST answer it gets as its baseline — the page was just
served by that same process, so that answer describes the code now running in the tab. Nothing has to be
injected into `index.html` at build time for that to be true.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import version

_HERE = Path(__file__).resolve().parent
_ENGINE = _HERE.parent

#: The build number, as shipped. Bump with `python -m update bump` — the release procedure does this
#: BEFORE cutting the tag (`.meshkore/docs/ops/zaelar-cloud-release.md`, step 3).
BUILD_FILE = _HERE / "BUILD"

_UI_ROOT = _ENGINE / "frontend"
#: What a browser actually fetches and runs. Deliberately an allowlist: `frontend/` also holds ~17 MB of
#: vendored wasm/onnx model blobs whose bytes cannot change without one of these changing too, and hashing
#: them would turn a 5 ms digest into a second of boot for no added truth.
_UI_SUFFIXES = (".js", ".mjs", ".css", ".html", ".webmanifest")

UNKNOWN = "unknown"

_CACHE: dict = {}


def build() -> int:
    """The user-facing version number (cached). 0 when the file is missing or unreadable — callers show
    the semantic version instead rather than inventing a number."""
    if "build" not in _CACHE:
        try:
            _CACHE["build"] = int(BUILD_FILE.read_text(encoding="utf-8").strip() or 0)
        except Exception:  # noqa: BLE001  — a missing/corrupt file is «unknown», never a crash at boot
            _CACHE["build"] = 0
    return _CACHE["build"]


def _digest_ui() -> str:
    h = hashlib.blake2b(digest_size=8)
    # A missing tree is «I cannot tell», not «the frontend is empty». The difference matters: an empty
    # digest is a perfectly stable value that every client would compare against happily, and the whole
    # channel would go quiet forever without anyone noticing.
    if not _UI_ROOT.is_dir():
        return UNKNOWN
    try:
        for p in sorted(q for q in _UI_ROOT.rglob("*") if q.suffix in _UI_SUFFIXES and q.is_file()):
            # The PATH goes into the digest too: renaming a module without touching a byte still changes
            # what the browser has to fetch.
            h.update(str(p.relative_to(_UI_ROOT)).encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    except Exception:  # noqa: BLE001
        return UNKNOWN
    return h.hexdigest()


def ui_rev() -> str:
    """Digest of the frontend the browser is running (cached for the life of the process — the files on
    disk cannot change under a running engine without a restart, which is a new process)."""
    if "ui" not in _CACHE:
        _CACHE["ui"] = _digest_ui()
    return _CACHE["ui"]


def state() -> dict:
    """The whole public payload. Every value is a constant after the first call: this is what makes the
    endpoint cheap enough to poll from every open tab."""
    return {
        "build": build(),
        "version": version.VERSION,
        "sha": version.sha(),
        "short": version.short(),
        "ui_rev": ui_rev(),
        "started_ms": version.started_ms(),
        # Which DEPLOYMENT answered. Set by the Dockerfile ("fly·cdg"); absent on a self-hosted engine.
        # It costs nothing and it is the field that makes «is this the cloud one or mine?» answerable
        # from the same place as the version.
        "deploy": os.getenv("DEPLOY_ENV", "").strip() or "local",
    }


def bump(step: int = 1) -> int:
    """Raise the build number and write it back. The ONE mutation in this module, and it is a release
    step run by a human or by CI — never by the engine at runtime."""
    n = build() + max(1, int(step))
    BUILD_FILE.write_text(f"{n}\n", encoding="utf-8")
    _CACHE["build"] = n
    return n
