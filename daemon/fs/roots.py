"""THE PERMISSION CIRCUIT — the one gate every filesystem operation goes through.

Everything the daemon can be asked to touch is checked here, and there is no second way in: nothing else in
`daemon.fs` builds a `Path` from caller input on its own. That is the whole design. A permission check that
lives at three call sites is a permission check that will one day live at two.

THE RULES, in the order they are applied to every path:

  1. It must be a non-empty string, and `~` is expanded (a user types `~/Documents`, not `/Users/x/Documents`).
  2. Windows syntax that reaches PAST a name — an alternate data stream, a UNC share, a device name — is
     refused before anything else looks at it, because after resolution those are invisible.
  3. It must be ABSOLUTE. Relative paths are refused rather than joined to something: the daemon has no
     meaningful working directory, and "relative to what?" is exactly the ambiguity path bugs live in.
  4. It is RESOLVED, which normalizes `..` and FOLLOWS EVERY SYMLINK.
  5. The RESOLVED path is checked against the never-served list (`daemon.security.denylist`).
  6. The RESOLVED path must lie inside one of the RESOLVED allowed roots.

Steps 4-6 in that order are the point. Checking before resolving is the classic hole: `~/Documents/../.ssh` and
a symlink `~/Documents/shortcut → ~/.ssh` both look like they are inside Documents until you resolve them, and
neither does afterwards. Resolving the ROOTS too is the other half, and it is not symmetry for its own sake: on
macOS `~/Documents` is frequently a symlink into `~/Library/Mobile Documents/…` when iCloud Drive is on, so a
check that resolved only the request would refuse the user their own Documents folder — the failure in the
OTHER direction, which is why the tests assert both.

WHY `Boundary` IS AN OBJECT. Resolving the allowlist means reading the config and calling `Path.resolve()` on
every root, which is a handful of syscalls. `list_dir` and `search` ask about thousands of paths, and doing that
per path turned a permission check into a per-entry filesystem storm — a listing of ten thousand files paid for
ten thousand root resolutions. One `Boundary` is built per request and answers all of them, so the check gets
cheaper without getting weaker. The module-level functions are the same thing for a single question.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..paths import default_documents, state_dir
from ..security import denylist
from .refusal import Refusal

# Directories that are never "the user's documents", whatever they answer. Granting one of these is either a
# mistake or a prompt-injected agent talking the user into one, and in both cases the honest answer is to say
# what the folder actually is and ask for a narrower one.
_SYSTEM_ROOTS = (
    "/", "/usr", "/etc", "/var", "/bin", "/sbin", "/opt", "/dev", "/proc", "/sys", "/tmp",
    "/System", "/Library", "/Applications", "/Volumes", "/private", "/Network",
    "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)", "C:\\ProgramData", "C:\\Users",
)


def _normalize(raw: str) -> Path:
    """Steps 1-4: everything up to and including resolution. Raises `Refusal`, never returns something unsafe."""
    if not isinstance(raw, str) or not raw.strip():
        raise Refusal("bad_path", "No path was given.")

    windows_shape = denylist.windows_reason(raw)
    if windows_shape:
        raise Refusal(
            "bad_path",
            f"'{raw.strip()}' is {windows_shape}, not a file I can open. Give me the path to a real file.",
        )

    try:
        expanded = Path(raw.strip()).expanduser()
    except Exception:           # noqa: BLE001 — malformed input, not a filesystem problem
        raise Refusal("bad_path", f"That is not a usable path: {raw!r}") from None

    if not expanded.is_absolute():
        raise Refusal(
            "relative_path",
            f"'{raw}' is a relative path and I have no folder to measure it from. Give me the full path.",
        )

    # strict=False so a not-yet-existing path still gets normalized: the boundary check below has to run on it
    # either way. On Windows this also expands 8.3 short names, which would otherwise let `PROGRA~1` walk past
    # a check written against the long name.
    try:
        return expanded.resolve(strict=False)
    except Exception:           # noqa: BLE001 — e.g. a symlink loop
        raise Refusal("bad_path", f"I could not resolve '{raw}' — it may be a broken or looping link.") from None


class Boundary:
    """The allowlist, resolved once, answering many questions."""

    __slots__ = ("roots", "_state")

    def __init__(self, roots: list[Path], state: Path | None = None):
        self.roots = roots
        self._state = state

    @classmethod
    def current(cls) -> Boundary:
        """The allowlist as it stands right now. A root that no longer exists is DROPPED rather than refused
        later with a confusing message — a folder the user deleted is not a permission problem."""
        out: list[Path] = []
        seen: set[str] = set()
        for raw in config.load().get("roots", []):
            try:
                resolved = Path(raw).expanduser().resolve()
            except Exception:   # noqa: BLE001 — an unresolvable entry is simply not a root
                continue
            if not resolved.is_dir():
                continue
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                out.append(resolved)
        try:
            state = state_dir().resolve()
        except Exception:       # noqa: BLE001 — a state dir we cannot resolve is one we cannot leak either
            state = None
        return cls(out, state)

    def as_strings(self) -> list[str]:
        return [str(p) for p in self.roots]

    def contains(self, resolved: Path) -> bool:
        return any(resolved == root or resolved.is_relative_to(root) for root in self.roots)

    def check(self, raw: str, *, must_exist: bool = True) -> Path:
        """Turn whatever the caller sent into a path the daemon is allowed to touch, or raise `Refusal`.

        `must_exist=False` is for `grant()` and for the write path (P5), where the target legitimately may not
        be there yet; the allowlist and denylist checks are identical either way, because a path outside the
        boundary is outside it whether or not it exists."""
        target = _normalize(raw)

        # The daemon's own state directory holds the API token. Nobody reads it through the daemon, ever,
        # including somebody who granted the whole workspace as a folder.
        if self._state is not None and (target == self._state or target.is_relative_to(self._state)):
            raise Refusal("protected", "That is the daemon's own configuration; I never read it out.")

        sensitive = denylist.reason_for(target)
        if sensitive:
            raise Refusal(
                "sensitive",
                f"I will not open '{target.name}': '{sensitive}' is on the list of things I never read "
                f"(keys, credentials and password stores), even inside a folder you allowed.",
            )

        if not self.roots:
            raise Refusal(
                "no_folders",
                "You have not given me access to any folder yet. Open the daemon panel and choose which "
                "folders I may read.",
                folders=[],
            )

        if self.contains(target):
            if must_exist and not target.exists():
                raise Refusal("not_found", f"There is nothing at '{target}'.")
            return target

        raise Refusal(
            "outside_allowlist",
            f"'{target}' is outside the folders you allowed me. Right now I can read: "
            + ", ".join(self.as_strings())
            + ". You can add another folder from the daemon panel.",
            folders=self.as_strings(),
        )


# ── the single-question form ──────────────────────────────────────────────────────────────────────────────

def roots() -> list[str]:
    """The allowlist as the engine and the wizard see it."""
    return Boundary.current().as_strings()


def resolve(raw: str, *, must_exist: bool = True) -> Path:
    return Boundary.current().check(raw, must_exist=must_exist)


# ── changing it ───────────────────────────────────────────────────────────────────────────────────────────

def _too_broad_reason(target: Path) -> str | None:
    """Is this a folder that is never "the user's documents"? Returns what it is, or None."""
    if target == Path(target.anchor):
        return "the whole disk"
    try:
        if target == Path.home().resolve():
            return "your entire home folder"
    except Exception:           # noqa: BLE001 — no home is not a reason to refuse everything
        pass
    for system in _SYSTEM_ROOTS:
        try:
            if target == Path(system).resolve():
                return f"a system folder ({system})"
        except Exception:       # noqa: BLE001 — a path this platform does not have
            continue
    return None


def grant(raw: str) -> list[str]:
    """Add a folder to the allowlist. Returns the new allowlist.

    Granting does NOT go through `check()`: that asks "is this inside the allowlist", and the whole point here is
    that it is not yet. It DOES go through the same normalization and the same denylist, so the user cannot hand
    the daemon `~/.ssh` by way of the wizard — the boundary has to hold at the point where folders are ADDED, or
    every later check will agree the key is allowed."""
    target = _normalize(raw)

    if not target.is_dir():
        raise Refusal("not_a_folder", f"'{target}' is not a folder I can open.")

    sensitive = denylist.reason_for(target)
    if sensitive:
        raise Refusal(
            "sensitive",
            f"I will not take '{target}' as a folder: '{sensitive}' is on the list of things I never read.",
        )

    broad = _too_broad_reason(target)
    if broad:
        raise Refusal(
            "too_broad",
            f"'{target}' is {broad}. Choose the folders you actually want me to work with instead — you can "
            f"always add more later.",
        )

    current = list(config.load().get("roots", []))
    if str(target) not in current:
        current.append(str(target))
    config.save({"roots": current, "configured": True})
    return roots()


def revoke(raw: str) -> list[str]:
    """Remove a folder from the allowlist. Matches on the RESOLVED form, so revoking `~/Documents` removes the
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

    `suggested` is where "Documents by default" actually lives. A fresh install grants NOTHING; Documents is the
    entry the wizard pre-checks, so a user who clicks straight through ends up with exactly the documented
    default — having been shown it, which is the difference that matters.

    Sensitive folders are omitted rather than shown-and-refused: offering `~/.ssh` in a picker and then refusing
    it is a worse conversation than never offering it."""
    home = Path.home()
    names = ["Documents", "Desktop", "Downloads", "Pictures", "Photos", "Music", "Movies", "Videos", "Projects"]
    documents = default_documents()
    boundary = Boundary.current()
    allowed = set(boundary.as_strings())
    out: list[dict] = []
    seen: set[str] = set()

    def _add(path: Path, label: str) -> None:
        try:
            resolved = path.resolve()
        except Exception:       # noqa: BLE001
            return
        if not resolved.is_dir() or str(resolved) in seen:
            return
        if denylist.reason_for(resolved) or _too_broad_reason(resolved):
            return
        seen.add(str(resolved))
        out.append({
            "path": str(resolved),
            "label": label,
            "allowed": str(resolved) in allowed,
            "suggested": documents is not None and resolved == documents,
        })

    for name in names:
        _add(home / name, name)
    # Anything the user already allowed that is not one of the usual names still belongs in the list, or the
    # wizard would show it as unchecked and re-granting would look like the only option.
    for path in boundary.roots:
        _add(path, path.name or str(path))
    return out


__all__ = ["Boundary", "Refusal", "roots", "resolve", "grant", "revoke", "candidates"]
