"""Demo pass 52 (2026-09-29), V5→V6: «go back to the list of videos» — the verdict read youtube:show_tab at 0.97, the
model called clear_search, which ERASES the results band (it was declared a `view`, which it is not), and «put on
number five… yeah five» then found no list. A lens the verdict is sure of changes nothing; a model call that changes
the card's state over it is the costly reading, so the lens runs."""

from nucleo.flash import data_ops



def test_clear_search_is_not_a_lens():
    assert not data_ops.is_view_op("youtube", "clear_search"), "it erases the list «put on number five» reads"
    assert data_ops.is_view_op("youtube", "show_tab")
