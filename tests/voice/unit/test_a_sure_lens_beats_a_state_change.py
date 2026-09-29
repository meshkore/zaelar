"""Demo pass 52 (2026-09-29), V5→V6: «go back to the list of videos» — the verdict read youtube:show_tab at 0.97, the
model called clear_search, which ERASES the results band (it was declared a `view`, which it is not), and «put on
number five… yeah five» then found no list. A lens the verdict is sure of changes nothing; a model call that changes
the card's state over it is the costly reading, so the lens runs."""
import pathlib

from nucleo.flash import data_ops

SRC = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")


def test_clear_search_is_not_a_lens():
    assert not data_ops.is_view_op("youtube", "clear_search"), "it erases the list «put on number five» reads"
    assert data_ops.is_view_op("youtube", "show_tab")


def test_the_voice_runs_the_sure_lens_over_a_state_change():
    i = SRC.index("la vista segura gana a un cambio de estado")
    block = SRC[SRC.rindex("if (_data_ops.is_view_op(_cd[\"card\"], _dis)", 0, i):i]
    assert "not _data_ops.is_view_op(_cd[\"card\"], action_name)" in block
    assert "_direct_action._action_sure(_brief, floor=0.9)" in block
    assert "instead_of=action_name" in block
