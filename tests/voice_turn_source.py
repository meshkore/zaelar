"""The source of the VOICE TURN, for the tests that guard it by reading its code (V2-778 F1-10, 2026-10-01).

Until F1-10 the voice turn was one coroutine, `_run_inner` in `voice/engine/llm/providers/nucleo.py`, and ~60
source guards read that one file. F1 splits it: the tool executor now lives in `nucleo/flash/tool_executor.py`
and is built by the provider per turn. The guards still ask the same question — «does the voice turn do X, and
before Y?» — so they read the turn's code as it runs: the provider with the executor's body put back where it
used to sit (just before `_tool_fired`), at its old indentation. Their positional assertions keep their meaning.

This is a reading aid for source guards, not a runtime: a behavioural test builds the executor itself.
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
PROVIDER = ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py"
EXECUTOR = ENGINE / "nucleo" / "flash" / "tool_executor.py"

_ANCHOR = "        _tool_fired: set = set()\n"
_BODY_START = '    `on_tool_call`, `resolve_confirm`, `start_web_auth`."""\n'
_BODY_END = "    return SimpleNamespace("


def executor_body() -> str:
    """The closures of `tool_executor.build`, re-indented to where they sat inside `_run_inner`."""
    src = EXECUTOR.read_text(encoding="utf-8")
    i = src.index(_BODY_START) + len(_BODY_START)
    j = src.index(_BODY_END, i)
    return "".join(("    " + ln) if ln.strip() else ln for ln in src[i:j].splitlines(True))


def turn_source() -> str:
    """The voice turn's code: the provider with the executor spliced back at its old place."""
    prov = PROVIDER.read_text(encoding="utf-8")
    k = prov.index(_ANCHOR)
    return prov[:k] + executor_body() + prov[k:]


def read(path) -> str:
    """`Path.read_text` for a source guard: the provider path yields the whole turn, anything else its file."""
    p = Path(path)
    if not p.is_absolute():
        p = ENGINE / p
    if p.resolve() == PROVIDER.resolve():
        return turn_source()
    return p.read_text(encoding="utf-8")
