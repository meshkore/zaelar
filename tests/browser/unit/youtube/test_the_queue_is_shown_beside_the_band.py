"""Node 2.597 — with the search band on screen the digest still shows the QUEUE, numbered by its own order.

`find-videos-on-a-topic-no-ai-slop` (EN, 2026-10-14): six results on the band AND the same six in the queue; the
digest replaced the queue's items line with the band, so «just the Palm Centre one, drop the rest» became
`remove {items: "2,3,4,6"}` by the band's numbers — the emoji video he complained about stayed. And with the queue
EMPTY nothing said so, which is how `clear_list` read as a sensible order.

Disarm: drop the `queue_line` append from `data.prompt_digest` → red.
"""
from __future__ import annotations

from ._band import EN, card, seed  # noqa: F401 — `card` is the fixture


def test_the_digest_numbers_the_queue_apart_from_the_band(card):  # noqa: F811
    seed(EN, queue=(1, 5))
    d = card.prompt_digest()
    line = next(ln for ln in d.splitlines() if ln.startswith("COLA"))
    assert "1. Tutorial how to prune" in line and "2. How to Prune an Olive Tree" in line, line


def test_an_empty_queue_is_said_beside_the_band(card):  # noqa: F811
    seed(EN)
    assert any(ln.startswith("COLA: vacía") for ln in card.prompt_digest().splitlines())
