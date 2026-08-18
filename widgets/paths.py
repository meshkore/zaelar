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
    """`<workspace>/widgets` — where a NEWLY generated widget's code goes. Resolved per call, not at import:
    the workspace is an env knob and a test (or a sandbox boot) may set it after this module is imported."""
    return os.path.join(str(_workspace.root()), "widgets")


def roots() -> list[str]:
    """Every directory that can hold widget folders, generated first. One entry when they coincide (the
    self-host default) — so no caller ever scans the same directory twice."""
    gen = generated_root()
    return [gen] if os.path.abspath(gen) == os.path.abspath(BUILTIN_ROOT) else [gen, BUILTIN_ROOT]


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
