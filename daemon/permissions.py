"""THE PERMISSION CIRCUIT — the one gate every filesystem operation goes through.

Everything the daemon can be asked to touch is checked here, by `resolve()`, and there is no second way in:
`files.py` never builds a `Path` from user input on its own. That is the whole design. A permission check that
lives at three call sites is a permission check that will one day live at two.

THE RULES, in the order they are applied to every path:

  1. It must be a non-empty string, and `~` is expanded (a user types `~/Documents`, not `/Users/x/Documents`).
  2. It must be ABSOLUTE. Relative paths are refused rather than joined to something — the daemon has no
     meaningful working directory, and "relative to what?" is exactly the ambiguity that path bugs live in.
  3. It is RESOLVED (`Path.resolve()`), which normalizes `..` and FOLLOWS EVERY SYMLINK.
  4. The RESOLVED path is checked against the sensitive-name list (below).
  5. The RESOLVED path must lie inside one of the RESOLVED allowed roots.

Steps 3-5 in that order are the point. Checking before resolving is the classic hole: `~/Documents/../.ssh` and
a symlink `~/Documents/shortcut → ~/.ssh` both look like they are inside Documents until you resolve them, and
both stop looking like it afterwards. Resolving the ROOTS too is the other half, and it is not symmetry for its
own sake: on macOS `~/Documents` is frequently a symlink into `~/Library/Mobile Documents/…` when iCloud Drive
is on, so a check that resolved only the request would refuse the user their own Documents folder — the failure
in the OTHER direction, which is why the tests assert both.

REFUSALS NAME THE BOUNDARY (V2-421/V2-507). A bare 403 makes the agent guess, and a guessing agent tells the
user something invented. Every refusal here carries the path it was asked for, why it was refused, and — when
the reason is the allowlist — which folders ARE available, so the engine can say something true.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import config
from .paths import default_documents, state_dir


class Refusal(Exception):
    """A refusal that can be reported honestly. `code` is for the engine, `message` is for the user, `folders`
    carries the allowlist when the reason is that the path is outside it."""

    def __init__(self, code: str, message: str, folders: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.folders = folders or []

    def as_dict(self) -> dict:
        d = {"ok": False, "error": self.code, "message": self.message}
        if self.folders:
            d["folders"] = self.folders
        return d


# Names that are never served, at any depth, even inside a folder the user granted. This is deliberately NOT
# overridable in v1: "the user allowed their home directory" must not mean "the agent may read the SSH key". The
# match is on the exact segment name, case-insensitively, because the filesystems this runs on are usually
# case-insensitive and `.SSH` would otherwise walk straight through.
_DENIED_SEGMENTS = frozenset({
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store",
    "gcloud", "keychains", ".gem", ".cargo", "credentials",
})

# Exact filenames that are credentials by convention.
_DENIED_NAMES = frozenset({
    ".env", ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".htpasswd",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.json", "zaelar.env",
})

# Extensions that are private keys or key stores. `.key` occasionally means something innocent; refusing it and
# saying so is the cheaper mistake of the two.
_DENIED_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".asc", ".gpg"})


def _resolved_roots() -> list[Path]:
    """The allowlist, resolved and deduplicated. A root that no longer exists is dropped rather than refused
    later with a confusing message — a folder the user deleted is not a permission problem."""
    out: list[Path] = []
    seen: set[str] = set()
    for raw in config.load().get("roots", []):
        try:
            p = Path(raw).expanduser().resolve()
        except Exception:       # noqa: BLE001 — an unresolvable entry is simply not a root
            continue
        if not p.is_dir():
            continue
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def roots() -> list[str]:
    """The allowlist as the engine and the wizard see it."""
    return [str(p) for p in _resolved_roots()]


def _sensitive_reason(p: Path) -> str | None:
    """Does this resolved path cross the never-served list? Returns the offending segment, or None."""
    parts = [seg.lower() for seg in p.parts]
    for seg in parts:
        if seg in _DENIED_SEGMENTS:
            return seg
    name = p.name.lower()
    if name in _DENIED_NAMES:
        return p.name
    if p.suffix.lower() in _DENIED_SUFFIXES:
        return f"*{p.suffix.lower()}"
    return None


def resolve(raw: str, *, must_exist: bool = True) -> Path:
    """Turn whatever the caller sent into a path the daemon is allowed to touch, or raise `Refusal`.

    `must_exist=False` is for the write path (P5) and for `grant()`, where the target legitimately may not be
    there yet; the allowlist and sensitivity checks are identical either way, because a path that is outside the
    boundary is outside it whether or not it exists."""
    if not isinstance(raw, str) or not raw.strip():
        raise Refusal("bad_path", "No path was given.")

    try:
        expanded = Path(raw.strip()).expanduser()
    except Exception:           # noqa: BLE001 — malformed input, not a filesystem problem
        raise Refusal("bad_path", f"That is not a usable path: {raw!r}") from None

    if not expanded.is_absolute():
        raise Refusal(
            "relative_path",
            f"'{raw}' is a relative path and I have no folder to measure it from. Give me the full path.",
        )

    # Follows symlinks and collapses `..`. strict=False so a not-yet-existing path still gets normalized — the
    # boundary check below must run on it either way.
    try:
        target = expanded.resolve(strict=False)
    except Exception:           # noqa: BLE001 — e.g. a symlink loop
        raise Refusal("bad_path", f"I could not resolve '{raw}' — it may be a broken or looping link.") from None

    # The daemon's own state directory holds the API token. Nobody reads it through the daemon, ever, including
    # somebody who granted the whole repo as a folder.
    try:
        if target == state_dir() or target.is_relative_to(state_dir()):
            raise Refusal("protected", "That is the daemon's own configuration; I never read it out.")
    except Refusal:
        raise
    except Exception:           # noqa: BLE001 — is_relative_to on odd paths
        pass

    sensitive = _sensitive_reason(target)
    if sensitive:
        raise Refusal(
            "sensitive",
            f"I will not open '{target.name}': '{sensitive}' is on the list of things I never read "
            f"(keys, credentials and password stores), even inside a folder you allowed.",
        )

    allowed = _resolved_roots()
    if not allowed:
        raise Refusal(
            "no_folders",
            "You have not given me access to any folder yet. Open the daemon panel and choose which folders "
            "I may read.",
            folders=[],
        )

    for root in allowed:
        if target == root or target.is_relative_to(root):
            if must_exist and not target.exists():
                raise Refusal("not_found", f"There is nothing at '{target}'.")
            return target

    raise Refusal(
        "outside_allowlist",
        f"'{target}' is outside the folders you allowed me. Right now I can read: "
        + ", ".join(str(p) for p in allowed)
        + ". You can add another folder from the daemon panel.",
        folders=[str(p) for p in allowed],
    )


def open_read(target: Path) -> int:
    """Open an ALREADY-RESOLVED path for reading, refusing to follow a symlink at the final component.

    This closes the gap `resolve()` cannot: between resolving a path and opening it, something could replace the
    last component with a symlink pointing outside the allowlist. Because `resolve()` returned a path with no
    symlinks left in it, `O_NOFOLLOW` succeeding proves nothing changed in that window, and `O_NOFOLLOW` failing
    means something did — which is the only correct moment to refuse.

    Windows has no `O_NOFOLLOW`; there the flag degrades to 0 and the window stays open. That is a real,
    stated limit, not a solved problem."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        return os.open(target, flags)
    except OSError as e:
        if e.errno in (getattr(os, "ELOOP", 62), 62, 40):
            raise Refusal(
                "symlink_race",
                f"'{target}' turned into a link while I was opening it. I stopped rather than follow it.",
            ) from None
        raise Refusal("not_readable", f"I could not open '{target}': {e.strerror or e}") from None


def grant(raw: str) -> list[str]:
    """Add a folder to the allowlist. Returns the new allowlist.

    Granting does NOT go through `resolve()`: `resolve()` asks "is this inside the allowlist", and the whole
    point here is that it is not yet. It DOES go through the same normalization and the same sensitive-name
    check, so the user cannot hand the daemon `~/.ssh` by way of the wizard."""
    if not isinstance(raw, str) or not raw.strip():
        raise Refusal("bad_path", "No folder was given.")
    try:
        target = Path(raw.strip()).expanduser().resolve(strict=False)
    except Exception:           # noqa: BLE001
        raise Refusal("bad_path", f"That is not a usable folder: {raw!r}") from None
    if not target.is_dir():
        raise Refusal("not_a_folder", f"'{target}' is not a folder I can open.")
    sensitive = _sensitive_reason(target)
    if sensitive:
        raise Refusal(
            "sensitive",
            f"I will not take '{target}' as a folder: '{sensitive}' is on the list of things I never read.",
        )
    if target == Path(target.anchor):
        raise Refusal(
            "too_broad",
            f"'{target}' is the whole disk. Choose the folders you actually want me to work with instead.",
        )
    current = list(config.load().get("roots", []))
    if str(target) not in current:
        current.append(str(target))
    config.save({"roots": current, "configured": True})
    return roots()


def revoke(raw: str) -> list[str]:
    """Remove a folder from the allowlist. Matches on the resolved form, so revoking `~/Documents` removes the
    entry even when it was stored as the iCloud path it resolves to."""
    try:
        target = Path(str(raw).strip()).expanduser().resolve(strict=False)
    except Exception:           # noqa: BLE001
        raise Refusal("bad_path", f"That is not a usable folder: {raw!r}") from None
    kept = []
    for entry in config.load().get("roots", []):
        try:
            if Path(entry).expanduser().resolve(strict=False) == target:
                continue
        except Exception:       # noqa: BLE001 — an unresolvable entry compares unequal and stays
            pass
        kept.append(entry)
    config.save({"roots": kept, "configured": True})
    return roots()


def candidates() -> list[dict]:
    """What the install wizard offers the user to choose from: the obvious folders in their home directory, each
    marked with whether it is already allowed. Nothing here grants anything — it is a menu, not an action.

    `suggested` is where "Documents by default" actually lives. A fresh install grants NOTHING (see
    `config._defaults()`); Documents is the entry the wizard pre-checks, so a user who clicks straight through
    ends up with exactly the documented default — having been shown it, which is the difference that matters.

    Sensitive folders are omitted rather than shown-and-refused: offering `~/.ssh` in a picker and then refusing
    it is a worse conversation than never offering it."""
    home = Path.home()
    names = ["Documents", "Desktop", "Downloads", "Pictures", "Photos", "Music", "Movies", "Videos", "Projects"]
    documents = default_documents()
    allowed = {str(p) for p in _resolved_roots()}
    out: list[dict] = []
    seen: set[str] = set()

    def _add(p: Path, label: str) -> None:
        try:
            rp = p.resolve()
        except Exception:       # noqa: BLE001
            return
        if not rp.is_dir() or str(rp) in seen or _sensitive_reason(rp):
            return
        seen.add(str(rp))
        out.append({"path": str(rp), "label": label, "allowed": str(rp) in allowed,
                    "suggested": documents is not None and rp == documents})

    for name in names:
        _add(home / name, name)
    # Anything the user already allowed that is not one of the usual names still belongs in the list, or the
    # wizard would show it as unchecked and re-granting would look like the only option.
    for p in _resolved_roots():
        _add(p, p.name or str(p))
    return out
