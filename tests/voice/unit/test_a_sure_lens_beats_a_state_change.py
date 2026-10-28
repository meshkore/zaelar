"""Demo pass 52 (2026-09-29), V5→V6: «go back to the list of videos» — the verdict read youtube:show_tab at 0.97, the
model called clear_search, which ERASES the results band (it was declared a `view`, which it is not), and «put on
number five… yeah five» then found no list. A lens the verdict is sure of changes nothing; a model call that changes
the card's state over it is the costly reading, so the lens runs."""
from tests import voice_turn_source as _vts
import pathlib

from nucleo.flash import data_ops

SRC = _vts.read(pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py")


def test_clear_search_is_not_a_lens():
    assert not data_ops.is_view_op("youtube", "clear_search"), "it erases the list «put on number five» reads"
    assert data_ops.is_view_op("youtube", "show_tab")


def test_the_voice_runs_the_sure_lens_over_a_state_change():
    import inspect
    from nucleo.acts import card
    block = inspect.getsource(card.vetoes)
    assert "_do.is_view_op(wid, verdict_action) and not _do.is_view_op(wid, model_action)" in block
    assert "floor=VETO_SURE" in block and card.VETO_SURE <= 0.97, "the measured 0.97 still vetoes"
    assert "_card.vetoes(_brief, _cd[\"card\"], action_name, _dis)" in SRC
