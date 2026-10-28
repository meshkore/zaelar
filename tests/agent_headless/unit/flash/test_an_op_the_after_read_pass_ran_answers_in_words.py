# Demo pass in a sandbox, 2026-10-28, R3 «find me a free five days in her vacation and tell me the dates»:
#
#     jev turn-brief   request_type=order · wants_words=tell
#     model            read_widget(agenda, «List all meetings between 2026-12-20 and 2027-01-04»)
#     brain            🔁 leyó para una orden — la llamada, con lo leído   agenda → agenda:find_free
#     widget           data:find_free {date, to_date, duration_min: 1440, count: 5}      ← the five days, computed
#     ⚡ reply         «Got it — let me check what's on your calendar through that stretch.»
#
# The op that ANSWERS (`find_free` declares `output.answer`) ran, and its answer was never said: the block that speaks
# an op's answer stands down whenever the turn READ a card — right when the read's own words answer — and the
# after-read pass had made the read's turn an op's turn without telling it. The read lane now marks the op it ran
# (`read_req["op"]`), and `data_ops.answer_owed` is the one reader of «does this turn owe an op's words».
from __future__ import annotations

from nucleo.flash import data_ops as _do


def test_a_read_that_answered_owes_no_op_words():
    assert _do.answer_owed({"v": {"widget_id": "agenda"}}, {"v": None}) is False


def test_a_read_whose_after_read_pass_ran_an_op_owes_that_ops_words():
    assert _do.answer_owed({"v": {"widget_id": "agenda"}, "op": {"widget_id": "agenda", "action": "find_free"}},
                           {"v": None}) is True


def test_a_turn_with_no_read_owes_its_ops_words_as_before():
    assert _do.answer_owed({"v": None}, {"v": None}) is True


def test_a_worker_took_the_turn_so_no_op_words_are_owed():
    assert _do.answer_owed({"v": None, "op": {"widget_id": "agenda", "action": "find_free"}}, {"v": "an errand"}) is False
