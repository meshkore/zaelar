"""An error handler that can crash is not an error handler (2026-08-23).

The harness reported it with the run that killed it: `cheapest-monitor` died on turn 10 with an HTTP 500, and the
engine log contained `IndexError: list index out of range` from

    _err = str(e).splitlines()[0][:200]

`"".splitlines()` is `[]`, so ANY exception without a message —`TimeoutError()`, `CancelledError()`, a bare
`RuntimeError('')`— makes the line crash on its own.

What makes it serious is WHERE it was: all fifteen copies lived inside an `except`, and the one in `probe.py`
is the handler that classifies the provider failure and decides the chain RELAY. A provider failing silently took
down the failure handler — the turn returned 500 and **the relay never happened**. The safety net broke precisely
when it was needed, and the symptom pointed to something else.
"""
import ast
import asyncio
import pathlib
import re

from nucleo.errors import brief

# parents[4], not [3]: this file lives one level deeper than `test_architecture_ratchet.py`. With [3] the
# scan pointed to `tests/`, so it reported its own docstring and did not find the engine.
ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_the_three_shapes_that_used_to_crash():
    """The three reproduced before writing anything. None raises, and none returns empty: a log that says
    «TimeoutError» is useful; a blank one is precisely what the original line was trying to avoid producing."""
    for exc in (TimeoutError(), asyncio.CancelledError(), RuntimeError("")):
        got = brief(exc)
        assert got == type(exc).__name__, got


def test_a_normal_message_keeps_its_first_line_and_its_cap():
    assert brief(ValueError("boom\nsegunda línea que no interesa")) == "boom"
    assert len(brief(ValueError("x" * 500))) == 200
    assert len(brief(ValueError("x" * 500), 50)) == 50


def test_a_str_that_itself_raises_does_not_take_the_handler_down():
    """Rare and real: C-wrapped errors with a `__str__` that crashes. If `brief` raised there, we would have
    changed one failure mode into another with the same effect."""
    class _Nasty(Exception):
        def __str__(self):
            raise RuntimeError("simulado")

    assert brief(_Nasty()) == "_Nasty"


def test_no_production_handler_slices_splitlines_without_a_guard():
    """The CLASS guard. Fifteen copies of one line are fifteen opportunities to fix fourteen.

    The form is allowed when it is GUARDED by a ternary that requires text (as in `music_flow.py`) or
    when the value comes from an already-checked source — therefore the same line is checked for a condition,
    instead of blindly banning the pattern and requiring it to be wrapped."""
    ofensores = []
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        # `tools/` is excluded: these are development scripts run manually, not handlers for the live engine,
        # which is what this guard concerns. Its only case has been confirmed to be safe — the read follows an
        # `if text and …` on the previous line — so nothing is being hidden; the subject is being narrowed.
        if any(x in rel.split("/") for x in (".venv", "tests", "tools", "__pycache__")) \
                or rel == "nucleo/errors.py":
            continue
        try:
            src = p.read_text()
        except Exception:
            continue
        for n, line in enumerate(src.splitlines(), 1):
            if "splitlines()[0]" not in line:
                continue
            if " if " in line:            # ternary that requires content — guarded
                continue
            ofensores.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not ofensores, ("un manejador vuelve a cortar `splitlines()[0]` sin guarda — usa "
                           "`nucleo.errors.brief(e)`:\n  " + "\n  ".join(ofensores))


def test_the_handler_that_decides_the_relay_uses_it():
    """The specific site that brought down the run: if it builds its message by hand again, the relay will break
    again when a provider fails silently.

    The first version anchored on «the FIRST occurrence of `provider_failure`» and used a text window, not
    a property: V2-309 added a mention higher up, the window moved, and the guard accused correct code
    (2026-08-25). What matters is that the handler's MESSAGE comes from the helper — so it anchors
    on the specific assignment, which is what decides the relay."""
    src = (ENGINE / "nucleo" / "flash" / "probe.py").read_text()
    assert "provider_failure" in src, "desapareció el manejador de fallo de proveedor del probe"
    assert "_err = _brief(" in src, (
        "el manejador del relevo dejó de usar el helper: si su mensaje se construye a mano, un proveedor "
        "cayendo en silencio vuelve a llevarse por delante al manejador del fallo")
    assert not re.search(r"str\(\w+\)\.splitlines\(\)\[0\]", src), "volvió la forma que revienta"
