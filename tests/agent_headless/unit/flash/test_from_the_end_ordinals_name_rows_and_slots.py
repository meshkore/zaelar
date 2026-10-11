"""Node 2.493 — «penúltimo» / «penultimate» / «second to last» / «antepenúltimo» are positions counted from the end, in
the one ordinal table (`widgets.refs._ORDINALS`) every reader shares: position refs, the queue's slot, and the
destination a move reads from his words.

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el penúltimo» named no row at all.
"""
from __future__ import annotations

import pytest

from nucleo.flash import move_fill as MF
from widgets import refs
from widgets.youtube import move_refs as mv


@pytest.mark.parametrize("said, idx", [
    ("el penúltimo", 3), ("la penúltima", 3), ("the penultimate one", 3), ("the second to last one", 3),
    ("the next to last", 3), ("el antepenúltimo", 2), ("the third to last", 2), ("el último", 4), ("last", 4),
])
def test_a_from_the_end_position_names_its_row(said, idx):
    assert refs.position_index(said, 5) == idx


def test_counting_past_the_start_names_nothing_and_no_number_word_is_negative():
    assert refs.position_index("el antepenúltimo", 2) is None
    assert all(n >= 1 for n in refs.number_words().values())


@pytest.mark.parametrize("said, slot", [("penúltimo", 3), ("second to last", 3), ("antepenúltima", 2), ("al final", 4)])
def test_the_queue_reads_it_as_a_slot(said, slot):
    assert mv.slot(said, 5) == slot


def test_a_move_reads_it_as_the_destination():
    slots, _spans = MF._destinations(MF._fold("ponlo el penúltimo"), 5)
    assert slots == {4}
    slots, _spans = MF._destinations(refs.from_the_end(MF._fold("put it second to last")), 5)
    assert slots == {4}
