"""Every block of the voice turn's prompt names its source and has a token budget that only goes down (refactor2710-08 T-05).

Measured on 784 real turns (2026-10-19..25): a median of 10.6 k system tokens, of which «CÓMO OPERAS» — 3.1 k — reads
no truth at all. The prose ratchet (`test_the_prompt_prose_only_shrinks`) counts bytes WHERE THEY ARE WRITTEN; this
counts TOKENS PER BLOCK of the prompt as it is BUILT (`builder.BLOCKS`, measured with `fast_client.est_tokens` — the
engine's own estimator), so a block that grows is named, not hidden in a total. The V2-526 rule, generalised: the
473-token messaging block was the first block with a budget; now every block has one.

The budgets are what a clean engine composes for an idle turn (empty screen, no memory, no errands). A per-turn block
that is empty here (memory, recall, live rows) is bounded by its own reader's caps; what is pinned here is the floor
every turn pays.

Disarm: add a sentence to `operating._flash_parts` and the operating budget goes red.
"""
from __future__ import annotations

import pytest

#: Tokens per block for an idle turn. EDIT DOWNWARD ONLY — the edit is the celebration. Measured 2026-10-28.
BUDGET = {
    "language": 254,
    "operating": 3140,     # ⚠️ reads NO truth: removing it is gated on the battery (×3), not on this test
    "resources": 2661,
    "close": 20,
}
#: How far under its budget a block may sit before the budget must be lowered.
SLACK = 30


@pytest.fixture
def idle_turn(monkeypatch):
    from nucleo.flash import memory_cache
    monkeypatch.setattr(memory_cache, "get", lambda: ("", ""))
    from nucleo.turn.prompt import builder
    timings: dict = {}
    builder.build_flash_system(turn_text="hola", timings=timings)
    return {k[4:]: v for k, v in timings.items() if k.startswith("tok_")}


def test_every_block_is_declared_with_its_source(idle_turn):
    from nucleo.turn.prompt import builder
    names = [n for n, _src in builder.BLOCKS]
    assert names == list(idle_turn), "a block is built that BLOCKS does not declare, or declared and never built"
    assert all(src.strip() for _n, src in builder.BLOCKS), "a block that names no source"
    sourceless = [n for n, src in builder.BLOCKS if src.startswith("NONE")]
    assert sourceless == ["operating", "close"], "a new block with no truth behind it"


@pytest.mark.parametrize("block", sorted(BUDGET))
def test_a_block_never_grows_past_its_budget(idle_turn, block):
    got = idle_turn[block]
    assert got <= BUDGET[block], (f"«{block}» is {got} tokens on an idle turn (budget {BUDGET[block]}): paid on EVERY "
                                  "turn by every operator. Find the mechanism the sentence stands in for.")
    assert BUDGET[block] - got <= SLACK, f"«{block}» shrank to {got}: lower its budget (was {BUDGET[block]})"


def test_an_idle_turn_pays_nothing_for_what_is_not_there(idle_turn):
    for block in ("memory", "recent", "recall", "people", "directive", "packs"):
        assert idle_turn[block] == 0, f"«{block}» costs tokens on a turn that has none of it"
