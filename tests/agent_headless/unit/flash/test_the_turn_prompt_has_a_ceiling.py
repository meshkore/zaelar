"""The system prompt the fast turn sends has a ceiling, measured on a clean install (V2-778 F2-19, 2026-10-02).

`test_the_prompt_prose_only_shrinks` counts the prose WRITTEN in the prompt modules; nothing measured what is
SENT — the composed `build_flash_system`, which also carries every open card's descriptors, the memory state and
the live state. Measured in a FRESH interpreter with the bank's own isolation (no operator data) on 2026-10-02 —
identical from a shell, alone under pytest and at the end of the whole flash chunk:

    0 cards open   24_115 chars
    2 cards open   29_091 chars  (agenda + mensajeria: the everyday screen) — the audit's target is 30_000
    6 cards open   37_151 chars  (each open card adds ~2 k of its declared actions)

Frozen DOWN-ONLY. The small margin absorbs what the live state legitimately varies by (the day's name, the
date). A raise is not an edit to this file: it is a reason to look at what grew.
"""
from __future__ import annotations

import pytest

MARGIN = 64
CEILINGS = {(): 24_115, ("agenda", "mensajeria"): 29_091,
            ("agenda", "mensajeria", "youtube", "contactos", "results", "musica"): 37_151}
TARGET_EVERYDAY = 30_000


_SNIPPET = """
import json, sys
from tests.brain.harness import Isolated
with Isolated("es"):
    from memory import api as memapi
    from nucleo.flash.prompt import build_flash_system
    out = {}
    for cards in json.loads(sys.argv[1]):
        memapi.set_state({"open_widgets": cards})
        out[",".join(cards)] = len(build_flash_system(timings={}, turn_text="¿qué tengo mañana?")[0])
print("SIZES" + json.dumps(out))
"""
_CACHE: dict = {}


def _measure(open_cards) -> int:
    """In a FRESH interpreter: what a clean install sends. Measured in-process the number moved with whatever an
    earlier test file had left in a module-level cache (+336 inside the flash chunk) — that is the suite's state,
    not the product's."""
    if not _CACHE:
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[4]
        r = subprocess.run([sys.executable, "-c", _SNIPPET, json.dumps([list(c) for c in CEILINGS])],
                           cwd=root, capture_output=True, text=True, timeout=120, env={**os.environ})
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SIZES")), "")
        assert line, f"the measurement did not run: {r.stderr[-800:]}"
        _CACHE.update(json.loads(line[5:]))
    return _CACHE[",".join(open_cards)]


@pytest.mark.parametrize("cards", list(CEILINGS))
def test_the_composed_prompt_does_not_grow(cards):
    n = _measure(cards)
    assert n <= CEILINGS[cards] + MARGIN, (
        f"with {list(cards) or 'no cards'} open the system prompt is {n} chars (ceiling {CEILINGS[cards]}). "
        f"Every char is paid on every turn: find what grew before raising anything.")


def test_the_everyday_screen_is_under_the_audits_target():
    assert _measure(("agenda", "mensajeria")) <= TARGET_EVERYDAY
