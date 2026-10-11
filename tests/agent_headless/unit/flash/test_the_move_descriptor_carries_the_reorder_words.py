"""Node 2.454 — `move`'s descriptor carries the reorder words under the 200-char cut; `sort_list` points at it.

Video-queue use case, regression sweep of 2026-10-11 (engine 3.36+2a5bd83c): «the third one before the second» (EN) —
verdict `youtube:move` 1.00, no call, «Done — Most Creative is now ahead of Los Goles» over an untouched queue; «cambia
el orden: el de skills ponlo antes que el de creative» (ES) — verdict split, a Brain Worker for ~100 s to swap two rows.
The green runs the day before were luck (the model happened to call `move {item: 2, to: 2}`).
"""
from __future__ import annotations

import json
import pathlib

from nucleo.flash import payload_fill as _pf
from nucleo.flash import turn_brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_the_move_descriptor_names_the_reorder_and_sort_points_at_it():
    acts = json.loads((_ENGINE / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))["actions"]
    cut = acts["move"]["desc"][:_tb.MAX_DESC_CHARS]
    for words in ("ORDEN", "antes que", "before"):
        assert words in cut, words
    assert {"before", "after"} <= set(acts["move"]["payload"])
    assert "move" in acts["sort_list"]["desc"][:_tb.MAX_DESC_CHARS]


def test_only_item_is_required_so_the_empty_turn_reaches_the_reorder_fill():
    assert _pf.fillable_key("youtube", "move") == ""
