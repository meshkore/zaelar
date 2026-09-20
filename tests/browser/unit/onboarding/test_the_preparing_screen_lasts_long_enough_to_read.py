"""The preparing screen lasts long enough to read, and says how far it has got (V2-731).

The operator, the moment after choosing a language: «ha salido como una pequeña
pantalla que ha durado un segundo o dos y no sé qué era. Si hay un loader o una
pantalla tiene que tener un progress bar o algo, pero como mínimo debe durar dos
segundos para que la gente lo vea».

For a preset language `prepare()` is instant, so `i18n/init/detect.py` emitted
"detected" and "ready" in the same breath and the veil faded 550 ms later. The
floor (`store.LANG_LOADER_FLOOR_MS`) is armed by `sse.js` on "detected" and holds
the veil however fast the language is ready; the bar is fed by the engine's own
step count, which is why this also pins that the server SENDS one.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_preparing_screen_lasts_long_enough_to_read.mjs")
DETECT = Path("i18n/init/detect.py")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_fast_language_still_leaves_a_screen_somebody_can_read():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_an_already_initialized_language_has_nothing_to_prepare():
    """«Si no hay que hacer nada para idiomas inicializados, mejor no mostrar NADA en ese caso.»

    Measured against the real module, not its source: a preset is zero steps by
    construction, and a language we would have to build is not.
    """
    from i18n import runtime as rt
    from i18n.init import aliases, detect, fillers

    assert detect._pending_steps("en") == [], "en is initialized — there is nothing to show a screen for"
    assert detect._pending_steps("es") == [], "es likewise"
    assert "en" in rt.PRESET and "es" in rt.PRESET, "and they are zero by CONSTRUCTION, not by disk state"

    # The opposite case is stated, not sampled: `i18n/generated/` is NOT sandboxed by the root conftest
    # (measured 2026-09-20), so asking the disk here would make the verdict depend on which languages this
    # machine happens to have tried.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rt, "missing_keys", lambda code: ["boot.encendiendo"])
        mp.setattr(aliases, "read", lambda code: {})
        mp.setattr(fillers, "read_smalltalk", lambda code: {})
        assert detect._pending_steps("ja") == ["bundle", "aliases", "smalltalk"], \
            "a language with no bundle, no alias pack and no phrasebook is three real pieces of work"
        mp.setattr(rt, "missing_keys", lambda code: [])
        mp.setattr(aliases, "read", lambda code: {"agenda": ["yotei"]})
        assert detect._pending_steps("ja") == ["smalltalk"], \
            "and one that only lacks its phrasebook is ONE — the count is of work, not of languages"


def test_each_check_mirrors_the_early_return_of_the_step_it_stands_for():
    """The count cannot claim work that will not happen, and cannot miss work that will.

    Each `ensure_*` returns immediately when its artefact is already on disk;
    `_pending_steps` asks the same question with the same reader. If one of them
    grows a second reason to no-op, this is the test that should fail.
    """
    src = DETECT.read_text(encoding="utf-8")
    body = src[src.index("def _pending_steps("):src.index("async def lock(")]
    assert "_rt.PRESET" in body and "missing_keys" in body, "the bundle's own early returns"
    assert "_aliases.read(" in body, "the alias pack is asked whether it exists"
    assert "read_smalltalk" in body, "so is the phrasebook"
    # an unreadable store means UNKNOWN, and unknown means we are going to work — never the other way
    assert body.count("steps.append") == 6, \
        "every check appends on failure too: a missed step is a wait with no screen"
    assert '"phase": "progress"' in src, "each finished step has to be reported"
    assert '"total": steps_total' in src, "the first event carries the denominator"


def test_a_step_that_was_not_pending_is_never_reported_as_progress():
    """A no-op that returns in a millisecond is not progress; counting it would put a bar on a screen
    with nothing behind it."""
    src = DETECT.read_text(encoding="utf-8")
    assert "if not onboarding or name not in pending:" in src, \
        "only PENDING steps may move the bar"


def test_a_progress_report_never_carries_the_language_code():
    """`sse.js` re-applies the language on ANY language event that has a `code`.

    A progress report with one would refetch the bundle once per step — for a
    screen whose only job is to say how far along it is.
    """
    body = DETECT.read_text(encoding="utf-8")
    start = body.index("    def _step(name: str) -> None:")
    end = body.index("    if onboarding:", start)
    assert '"code"' not in body[start:end], \
        "the progress event must not carry `code` — see sse.js's applyLang"
