#
# WHERE A WIDGET'S CODE LIVES — one answer, instead of six modules each computing `HERE/<id>/` on their own.
#
# A widget folder can come from two places and they are NOT the same kind of thing:
#
#   · BUILT-IN — ships inside the repo (`engine/widgets/<id>/`), versioned, the same for every install.
#   · GENERATED — written by `widgets/generator.py` when the operator asks for a widget that doesn't exist.
#     That is the operator's OWN content, born at runtime, and it belongs under the workspace
#     (`<workspace>/widgets/<id>/`) for exactly the reasons `nucleo/workspace.py` exists: it is per-tenant
#     state, not engine source.
#
# With `ZAELAR_WORKSPACE` unset — every self-host install, the operator's own machine — `workspace.root()` IS
# the repo root, so `generated_root()` resolves to the very same `engine/widgets/` directory and behaviour is
# BYTE IDENTICAL to before this module existed. Nothing moves, nothing needs migrating. Same contract
# `widgets/store.py` already made for widget DATA; this closes the half that was left open.
#
# What it fixes, measured (V2-125, `build-workout-tracker-widget`, 2026-08-18): a sandboxed use-case run wrote
# its generated widget into the operator's real `engine/widgets/`, so the NEXT run of the same scenario opened
# with «ya tienes ese widget» about a widget the simulated user had never asked for. The judge read it as a
# hallucination; the mechanism says the catalog was right and the isolation was wrong. It was a known leak,
# written down in `tests/platform/sandbox_engine.py`, deliberately left for the product to fix — the sandbox
# cannot sweep the folder afterwards because the operator's live engine may be generating into the same
# directory at that same moment and a cleanup pass cannot tell the two apart.
#
# It also stops the everyday nuisance that made the leak visible in the first place: generated widgets landing
# as untracked folders inside a git checkout.
#
# Resolution order is GENERATED first, then BUILT-IN. A generated widget that shadows a built-in id wins, which
# is what an operator who asked for their own version of something would expect — and it keeps the sandbox able
# to SEE the built-ins (the reason the naive "just make the catalog workspace-relative" fix was rejected).
#
import os

from nucleo import workspace as _workspace

BUILTIN_ROOT = os.path.dirname(os.path.abspath(__file__))


def generated_root() -> str:
    """Where a NEWLY generated (or forked) widget's code goes. Resolved per call, not at import: the
    workspace is an env knob and a test (or a sandbox boot) may set it after this module is imported.

    `<workspace>/widgets` when a workspace is mounted (the cloud Volume). On self-host — where the
    workspace IS the repo root — it is `widgets/_user/` instead of the repo folder itself (V2-515):
    the two roots must never collapse, because the collapse left a user's fork nowhere to live and
    made "delete/modify a widget" operate on engine source (measured 2026-08-30: a lab deleted
    `widgets/clock` and `widgets/musica` from the tree). `_user/` is gitignored, which also ends the
    old nuisance of generated widgets landing as untracked folders inside the checkout."""
    gen = os.path.join(str(_workspace.root()), "widgets")
    if os.path.abspath(gen) == BUILTIN_ROOT:
        return os.path.join(BUILTIN_ROOT, "_user")
    return gen


def roots() -> list[str]:
    """Every directory that can hold widget folders, generated first — the generated root shadows the
    built-in one. Also keeps the PYTHON import path in step (see `_sync_import_path`), so that
    `import widgets.<id>.data` resolves through the same two roots, in the same order, as the catalog."""
    gen = generated_root()
    out = [gen] if os.path.abspath(gen) == BUILTIN_ROOT else [gen, BUILTIN_ROOT]
    _sync_import_path(out)
    return out


def _sync_import_path(rts: list[str]) -> None:
    """Make the `widgets` package search modules through the SAME roots as the catalog (V2-515). Every
    consumer of a widget's python half does `import widgets.<id>.data` (server_api, background, refs,
    harness, validator, supervisor's `.owner`) — with the package's default `__path__` that only ever
    found folders inside the repo, so any widget living in the generated root (every cloud-generated
    widget, every fork) silently lost its backend: `_data_module` swallowed the ImportError and the
    widget ran with dead hooks. Idempotent, cheap (a list compare), refreshed on every `roots()` call
    because the workspace env can change after import (sandbox boots do exactly that)."""
    try:
        import widgets as _pkg
        if list(_pkg.__path__) != rts:
            _pkg.__path__[:] = rts
    except Exception:
        pass


def forget_modules(widget_id: str) -> None:
    """Evict a widget's imported python modules (`widgets.<id>` and below) so the NEXT import resolves
    the folder AGAIN through `roots()` (V2-515). Without this, a long-lived process that already
    imported the BUILT-IN's data.py keeps answering from it after a fork appears (or keeps answering
    from a deleted fork): `importlib.reload` re-reads the OLD spec's file, it does not re-resolve.
    Call it on every lifecycle transition that moves which folder owns the id — fork, delete, restore."""
    import sys
    wid = (widget_id or "").strip()
    if not wid:
        return
    prefix = f"widgets.{wid}"
    for name in [n for n in list(sys.modules) if n == prefix or n.startswith(prefix + ".")]:
        sys.modules.pop(name, None)


def dir_for(widget_id: str) -> str | None:
    """The folder of an EXISTING widget, or None. Generated shadows built-in."""
    wid = (widget_id or "").strip()
    if not wid:
        return None
    for base in roots():
        folder = os.path.join(base, wid)
        if os.path.isfile(os.path.join(folder, "manifest.json")):
            return folder
    return None


def new_dir(widget_id: str) -> str:
    """Where a widget being CREATED right now must be written. Always the generated root — a widget born at
    runtime is never engine source, even when the two directories happen to be the same one."""
    return os.path.join(generated_root(), (widget_id or "").strip())


def iter_folders():
    """(widget_id, folder) for every widget folder that exists, generated shadowing built-in. Yields folders,
    not manifests: whether a folder is a USABLE widget (manifest AND widget.js) is `runtime`'s call, and it
    deliberately skips half-built debris — that rule stays in one place."""
    seen: set[str] = set()
    for base in roots():
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            if name in seen or name.startswith((".", "_")):
                continue
            folder = os.path.join(base, name)
            if os.path.isdir(folder):
                seen.add(name)
                yield name, folder
