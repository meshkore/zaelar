"""The system prompt the fast turn sends has a ceiling, measured on a clean install (V2-778 F2-19, 2026-10-02).

`test_the_prompt_prose_only_shrinks` counts the prose WRITTEN in the prompt modules; nothing measured what is
SENT — the composed `build_flash_system`, which also carries every open card's descriptors, the memory state and
the live state. Measured in an isolated fixture (no operator data, the bank's own isolation), under the suite's own
environment, on 2026-10-02 (stable across runs and after other test files):

    0 cards open   24_533 chars
    2 cards open   29_259 chars  (agenda + mensajeria: the everyday screen) — the audit's target is 30_000
    6 cards open   36_759 chars  (each open card adds ~2 k of its declared actions)

Frozen DOWN-ONLY. The small margin absorbs what the live state legitimately varies by (the day's name, the
date). A raise is not an edit to this file: it is a reason to look at what grew.
"""
from __future__ import annotations

import pytest

MARGIN = 64
CEILINGS = {(): 24_533, ("agenda", "mensajeria"): 29_259,
            ("agenda", "mensajeria", "youtube", "contactos", "results", "musica"): 36_759}
TARGET_EVERYDAY = 30_000


def _measure(open_cards) -> int:
    from tests.brain.harness import Isolated
    with Isolated("es"):
        from memory import api as memapi
        from nucleo.flash.prompt import build_flash_system
        memapi.set_state({"open_widgets": list(open_cards)})
        prompt, _ = build_flash_system(timings={}, turn_text="¿qué tengo mañana?")
        return len(prompt)


@pytest.mark.parametrize("cards", list(CEILINGS))
def test_the_composed_prompt_does_not_grow(cards):
    n = _measure(cards)
    assert n <= CEILINGS[cards] + MARGIN, (
        f"with {list(cards) or 'no cards'} open the system prompt is {n} chars (ceiling {CEILINGS[cards]}). "
        f"Every char is paid on every turn: find what grew before raising anything.")


def test_the_everyday_screen_is_under_the_audits_target():
    assert _measure(("agenda", "mensajeria")) <= TARGET_EVERYDAY
