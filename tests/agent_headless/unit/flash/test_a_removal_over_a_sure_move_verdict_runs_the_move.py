"""Node 2.490 — a removal the model called over a SURE verdict naming another action of the same card never runs: the
verdict's action runs instead, filled from his words (text channel, `verdict_card.retarget`).

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el último… no, el penúltimo, ponlo justo después
del de skills» — `screen_action = youtube:move` 1.00, the model called `remove {item: 4}`, the video was deleted and
the reply said «Hecho.». Anything less certain keeps the model's call: an unsure verdict, a verdict that is itself a
removal, another card, or a sentence where he did say «quita».
"""
from __future__ import annotations

import pytest

from nucleo.flash import destructive_veto as DV
from nucleo.flash import verdict_card as VC
from widgets.youtube import data as yt

from ._imprecise_queue_scene import MOVED, QUEUE, SAID
from ._video_queue_scene import brief, queue, titles  # noqa: F401 — `queue` is a fixture


def test_the_move_runs_and_nothing_is_removed(queue):
    queue(QUEUE)
    wid, act, pl = VC.retarget(brief({"screen_action": ("youtube:move", 1.0)}), "youtube", "remove", {"item": "4"}, SAID)
    assert (wid, act) == ("youtube", "move"), (wid, act, pl)
    assert yt.apply_action(act, pl)["ok"]
    assert titles() == MOVED                       # five rows still: the penultimate sits right behind «skills»


def test_with_nothing_to_fill_the_card_asks_instead_of_removing(queue):
    queue(QUEUE)
    wid, act, pl = VC.retarget(brief({"screen_action": ("youtube:move", 0.95)}), "youtube", "remove", {"item": "2"},
                               "eso no, cámbialo")
    assert act == "move" and pl == {}
    r = yt.apply_action(act, pl)
    assert r["ok"] is False and r["error"] == "missing_item"     # «¿Cuál de los vídeos muevo?»
    assert titles() == QUEUE


@pytest.mark.parametrize("answers, said", [
    ({"screen_action": ("youtube:move", 0.85)}, SAID),           # under the bar: CRIT-K2, the model's call stands
    ({"screen_action": ("youtube:clear_list", 1.0)}, SAID),      # the verdict is a removal itself
    ({"screen_action": ("youtube:remove", 1.0)}, SAID),          # the verdict agrees
    ({"screen_action": ("youtube:move", 1.0)}, "quita el penúltimo y pon el primero al final"),   # he said «quita»
])
def test_anything_less_certain_keeps_the_models_call(queue, answers, said):
    queue(QUEUE)
    got = VC.retarget(brief(answers), "youtube", "remove", {"item": "4"}, said)
    assert got[1] == "remove", got


def test_a_non_destructive_model_call_is_not_this_rule(queue):
    queue(QUEUE)
    assert DV.contradicted(brief({"screen_action": ("youtube:move", 1.0)}), "youtube", "play_item", SAID) == ("", "")
    assert DV.removes("youtube", "remove") and DV.removes("youtube", "clear_list")
    assert not DV.removes("youtube", "move")
