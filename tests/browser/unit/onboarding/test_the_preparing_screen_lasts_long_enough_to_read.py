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


def test_the_engine_counts_its_own_preparation_steps():
    """The denominator is the engine's, not a guess in the frontend.

    A preset only has its bundle; a new language also generates the alias pack
    and the phrasebook — three steps, and the count travels WITH the first event
    so the bar never grows its own scale halfway through.
    """
    src = DETECT.read_text(encoding="utf-8")
    assert "steps_total = 1 if code in _rt.PRESET else 3" in src, \
        "the step count must follow what the preparation actually does"
    assert '"phase": "progress"' in src, "each finished step has to be reported"
    assert '"total": steps_total' in src, "the first event carries the denominator"


def test_a_progress_report_never_carries_the_language_code():
    """`sse.js` re-applies the language on ANY language event that has a `code`.

    A progress report with one would refetch the bundle once per step — for a
    screen whose only job is to say how far along it is.
    """
    body = DETECT.read_text(encoding="utf-8")
    start = body.index("    def _step() -> None:")
    end = body.index("    if onboarding:", start)
    assert '"code"' not in body[start:end], \
        "the progress event must not carry `code` — see sse.js's applyLang"
