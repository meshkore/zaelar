"""Node 2.491 — the voice rail asks the same rule: a removal over a sure verdict naming another action of the same card
dispatches the VERDICT's action (`verdict_card.takes_the_view` → `destructive_veto.run`), never the removal.

Same incident as node 2.490 («el último… no, el penúltimo, ponlo justo después del de skills», verdict `youtube:move`
1.00, model `remove {item: 4}`, «Hecho.» over a deleted video). What reaches `apply_widget_data` is the only thing the
card can execute, so that is what is asserted.
"""
from __future__ import annotations

from nucleo.flash import verdict_card as VC

from ._imprecise_queue_scene import QUEUE, SAID
from ._video_queue_scene import brief, queue  # noqa: F401 — `queue` is a fixture


def _voice(answers, action="remove", said=SAID):
    sent, seen = [], []
    got = VC.takes_the_view(brief(answers), "youtube", action, operator_text=said,
                            emit=lambda *a, **k: seen.append(a), present=lambda *a, **k: None,
                            apply_widget_data=lambda *a: sent.append(a))
    return got, sent, seen


def test_the_move_is_dispatched_and_the_removal_is_not(queue):
    queue(QUEUE)
    got, sent, seen = _voice({"screen_action": ("youtube:move", 1.0)})
    assert got == "move"
    assert sent == [("youtube", "move", {"item": "4", "after": "1"})], sent
    assert seen, "the swap is on the timeline"


def test_an_unsure_verdict_leaves_the_voice_rail_as_it_was(queue):
    queue(QUEUE)
    got, sent, _ = _voice({"screen_action": ("youtube:move", 0.8)})
    assert got == "" and sent == []
