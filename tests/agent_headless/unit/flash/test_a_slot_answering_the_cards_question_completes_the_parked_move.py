"""Node 2.462 — a slot that answers the card's own question completes the PARKED move, and a reply that only repeats
that refusal is not a new question: the verdict rung runs it, end to end, in the text channel's shape.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f), turn 6: «A la 1, ponlo el primero de todos» after
«Dime a qué posición (1-N) lo muevo» — verdict `youtube:move` 0.75, no call, the refusal repeated word for word, and the
rung stood down because the reply «asked for a detail». The question had been asked; he had just answered it.
"""
from __future__ import annotations

from nucleo.flash import direct_action as _da
from nucleo.flash import move_fill as _mf
from nucleo.flash import parked_refusal as _parked
from nucleo.flash import turn_brief as _tb
from nucleo.flash import undecided as _und
from widgets.youtube import data as yt

from ._video_queue_scene import brief, queue, titles  # noqa: F401 — `queue` is a fixture

ES_QUEUE = ["Diego Maradona 👑 Prime Argentina Skills, Goals, Dribbling & Tricks",
            "Opus - Live Is Life | Maradona Calentamiento 1989", "Los Goles Inolvidables de Diego Maradona",
            "Maradona - Anubiis x Hades 66 x  (Video Oficial)"]
HIS_ANSWER = "A la 1, ponlo el primero de todos."
PLAYING = ES_QUEUE[3]


#: The card's question as the operator hears it (`widgets.youtube.move_missing_position`): a question `clarifying`
#: reads as asking for a detail — which is what made the rung stand down on turn 6.
ASKED = "¿A qué posición de la cola lo muevo?"


def _park(payload: dict, message: str = ASKED):
    _parked.remember("youtube", "move", payload, {"ok": False, "error": "missing_position", "message": message})
    return message


def test_his_slot_completes_the_item_the_refused_call_carried(queue):
    queue(ES_QUEUE, pos=3)
    _park({"item": PLAYING, "to": "la luna"})
    assert _mf.move_fill("youtube", "move", HIS_ANSWER) == {"item": PLAYING, "to": 1}
    # …and the mirror: his row completes the slot the refused call carried
    _park({"item": "", "position": "first"}, "¿Cuál de los vídeos muevo?")
    assert _mf.move_fill("youtube", "move", "el que está sonando") == {"item": "4", "to": "first"}


def test_a_reply_that_repeats_the_refusal_is_not_a_new_question(queue):
    queue(ES_QUEUE, pos=3)
    msg = _park({"item": PLAYING, "to": "la luna"})
    from nucleo.flash import clarifying as _cl
    assert _cl.asks_for_missing_detail(f"No he podido: {msg}")          # the premise: it reads as a question
    assert _parked.parrots(f"No he podido: {msg}", "youtube", "move")
    assert _und.why(None, "youtube", "move", operator_text=HIS_ANSWER, model_words=f"No he podido: {msg}") == ""
    assert _und.why(None, "youtube", "move", operator_text=HIS_ANSWER, model_words="¿Cuál de los vídeos muevo?") == "asked"
    assert not _parked.parrots("¿Cuál de los vídeos muevo?", "youtube", "move")


def test_the_parked_question_goes_stale_when_the_card_changes_or_time_passes(queue):
    queue(ES_QUEUE, pos=3)
    _park({"item": PLAYING, "to": "la luna"})
    assert _parked.last("youtube", "move")
    assert _parked.last("youtube", "move", now=__import__("time").time() + _parked.WINDOW_S + 1) is None
    assert yt.apply_action("move", {"item": "2", "to": 3})["ok"]          # a later op landed on the card
    assert _parked.last("youtube", "move") is None
    assert _mf.move_fill("youtube", "move", HIS_ANSWER) == {}
    _park({"item": PLAYING, "to": "la luna"})
    _parked.remember("youtube", "move", {"item": PLAYING, "to": 1}, {"ok": True})   # a landed result forgets it
    assert _parked.last("youtube", "move") is None


def test_the_verdict_rung_runs_the_completed_move_end_to_end(queue, monkeypatch):
    queue(ES_QUEUE, pos=3)
    msg = _park({"item": PLAYING, "to": "la luna"})
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    b = brief({_tb.TARGET_KEY: ("youtube:move", 0.75), _tb.REQUEST_KEY: ("order", 1.0)})
    rung = _da.resolve(HIS_ANSWER, brief=b, operator_text=HIS_ANSWER, model_words=f"No he podido: {msg}")
    assert rung and rung["source"] == "said-move" and rung["payload"] == {"item": PLAYING, "to": 1}, rung
    assert yt.apply_action(rung["action"], rung["payload"])["ok"]
    assert titles()[0] == PLAYING and yt._load()["pos"] == 0
