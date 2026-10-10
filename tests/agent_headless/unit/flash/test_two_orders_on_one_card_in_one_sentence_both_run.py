"""V2-781 — «play the first one, queue the rest» ran half the sentence.

Measured in `la-cola-de-video-con-palabras-imprecisas` (ES and EN, 2026-10-10): over six results on the
player's Home, the model emitted exactly the right two calls —

    youtube.play_result {item: 1}
    youtube.add_results {items: "2,3,4,5,6"}

— and only the first ran. `data_ops.admite_data_op` refused the second because «a different action on the
same widget» is how the ENUMERATION looks (``done``/``drop``/``snooze`` over «show me the agenda»). The queue
stayed empty, so every later order on it — remove the third, move the last up, next, save it as «Maradona» —
failed with «I can't find that video in the list», and the reply had said «Done».

What tells the two apart is not the action names, it is WHAT each call is about. An enumeration offers
alternatives over the same thing (the same row, or no row at all); a sentence with two orders hands each
call its own, different target. So a second action on the same card runs when both calls name what they act
on and nothing they name is shared. The rule is the one both channels read (voice: `tool_executor_calls`).
"""
from __future__ import annotations

from nucleo.flash import data_ops as RG


def _op(wid, act, **payload):
    return {"widget_id": wid, "action": act, "payload": payload}


def test_play_one_and_queue_the_rest_both_run():
    play = _op("youtube", "play_result", item=1)
    queue = _op("youtube", "add_results", items="2,3,4,5,6")
    assert RG.admite_data_op(play, []) is True
    assert RG.admite_data_op(queue, [play]) is True


def test_move_one_and_save_the_list_both_run():
    move = _op("youtube", "move", item="6", to=2)
    save = _op("youtube", "save_list", name="Maradona")
    assert RG.admite_data_op(save, [move]) is True


def test_the_enumeration_over_the_same_row_still_does_not():
    """The reason the rule exists: alternatives over ONE row are a menu, not an order."""
    done = _op("agenda", "done", item=1)
    assert RG.admite_data_op(_op("agenda", "drop", item=1), [done]) is False
    assert RG.admite_data_op(_op("agenda", "snooze", item=1, minutes=10), [done]) is False


def test_an_action_that_names_nothing_is_still_a_menu():
    """A call with an empty payload says nothing about what it acts on — it cannot prove it is a second order."""
    play = _op("youtube", "play_result", item=1)
    assert RG.admite_data_op(_op("youtube", "next"), [play]) is False
    assert RG.admite_data_op(_op("youtube", "play_result", item=2), [_op("youtube", "pause")]) is False


def test_the_cap_still_holds():
    ya = [_op("youtube", "add", url=f"v{i}") for i in range(RG.MAX_DATA_OPS)]
    assert RG.admite_data_op(_op("youtube", "save_list", name="x"), ya) is False
