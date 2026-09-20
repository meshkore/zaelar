"""Node 3.61 — the blocking Jev callers are frozen at two, and the debt may only go down.

`jev.choose_sync` ends in `urllib.request.urlopen`: it blocks the calling thread for up to the
timeout (900 ms by default, against a measured p50 of 800 — V2-726 §1). Two callers do that from
inside the voice provider's `async def _run_inner`, which is the event loop STT, TTS and barge-in
all share, so a slow Jev call freezes the whole turn.

This is a RATCHET, not a fix: the two are recorded, and a third cannot appear without turning this
red. V2-726 F2 removes both by reading the verdict from the turn-start brief; when it does, this
list empties and the assertion says so.

Static on purpose. The alternative — proving at runtime that a coroutine stalled — needs a live
turn and a slow network, which is exactly the condition nobody can reproduce on demand.
"""
from __future__ import annotations

import ast
import pathlib

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_ROOTS = ("nucleo", "voice", "server", "widgets", "memory")

# The two measured in V2-726 §3.2. Shape: "<module path>::<enclosing function>".
KNOWN_BLOCKING = {
    "nucleo/flash/escalation_guard.py::judge_escalation",
    "nucleo/flash/frontend.py::repair_action",
}


def _blocking_callers() -> set[str]:
    """Every function in the engine that calls `choose_sync`, by `path::function`.

    `jev.py` itself is excluded: it DEFINES the blocking primitive, and `classify_sync` is its
    documented synchronous wrapper for tests and manual probes — neither is a caller on a path.
    """
    found: set[str] = set()
    for root in _ROOTS:
        for path in sorted((_ENGINE / root).rglob("*.py")):
            if path.name == "jev.py" or "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(_ENGINE).as_posix()
            funcs = [(n.lineno, getattr(n, "end_lineno", n.lineno), n.name)
                     for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name != "choose_sync":
                    continue
                enclosing = [f for f in funcs if f[0] <= node.lineno <= f[1]]
                enclosing.sort(key=lambda f: f[1] - f[0])          # innermost wins
                found.add(f"{rel}::{enclosing[0][2]}" if enclosing else f"{rel}::<module>")
    return found


def test_no_new_blocking_jev_caller_appears():
    """A third blocking caller is a third way to freeze a live turn. Add it to the brief instead."""
    found = _blocking_callers()
    new = found - KNOWN_BLOCKING
    assert not new, (
        f"new blocking `choose_sync` caller(s): {sorted(new)}. `choose_sync` blocks its thread on "
        f"urlopen and the voice path runs on the event loop — ask the question in the turn brief "
        f"(V2-726 F1) and peek the answer, or fire it with `ask_async`.")


def test_the_declared_blocking_debt_only_goes_down():
    """The other half of a ratchet: when F2 lands, this list must shrink, and the shrink is what
    proves it. Leaving a retired entry declared would hide the next regression behind it."""
    found = _blocking_callers()
    stale = KNOWN_BLOCKING - found
    assert not stale, (
        f"declared blocking callers that no longer exist: {sorted(stale)}. Remove them from "
        f"KNOWN_BLOCKING — a ratchet that over-declares stops catching anything.")


# The voice provider's coroutine, and the functions that would freeze it if it named them.
_PROVIDER = _ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"
BLOCKING_NAMES = ("judge_escalation", "repair_action", "choose_sync", "classify_sync")


def test_the_voice_provider_names_no_blocking_jev_call():
    """V2-726 F2's actual metric: 2 → 0. Not «does a blocking function exist» (it does, the probe
    channel uses it) but «can the voice turn reach one».

    The `_from_brief` readers are the supported door, and they share a prefix with the blocking ones
    on purpose — so this check strips the `_from_brief` spellings first and whatever remains is a
    real call. A new one here is a new way to freeze STT, TTS and barge-in for up to the timeout.
    """
    src = _PROVIDER.read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    code = code.replace("judge_escalation_from_brief", "").replace("repair_action_from_brief", "")
    hits = sorted({n for n in BLOCKING_NAMES if f"{n}(" in code})
    assert not hits, (
        f"the voice provider calls {hits} — those block the event loop on urlopen. Ask the question "
        f"in the turn brief (`nucleo/flash/turn_brief.py`) and read the verdict with `_from_brief`.")


def test_the_brief_readers_are_what_it_uses_instead():
    """The other half: F2 is not «stopped calling», it is «reads instead». Both must be true, or a
    silent removal of the gate would pass the check above."""
    src = _PROVIDER.read_text(encoding="utf-8")
    assert "judge_escalation_from_brief(" in src, "the escalate gate lost its brief reader"
    assert "turn_brief" in src, "the provider no longer fires the turn brief at all"
    assert "brief=_brief" in src, "the action repair no longer receives the brief"


def test_the_async_path_is_the_supported_one():
    """The non-blocking door exists and is what every hot-path caller is expected to use."""
    from nucleo import jev
    assert callable(jev.ask_async) and callable(jev.peek) and callable(jev.resolve_choice)
