"""Demo pass 2026-09-28 — which card an order means when it does not say.

E2: «open the most important one» right after the inbox came up read `results:detail`; U3: «pause it a sec» right
after the music started read `youtube:pause`. Two cards that can do the same thing differ in which one the
conversation is about, and the screen question carried nothing that said it. Measured with the live reader
(scratchpad jev_focus.py, 2026-09-28): 0/3 without the fact, 3/3 with it in the instructions, and the orders that
name a kind of thing («pause the video», «next song», «the second monitor in the results») 4/4 either way.
"""
from nucleo import canvas_focus as cf
from nucleo.flash import turn_brief as tb


def _q(monkeypatch, ids, focus):
    cf._reset()
    if focus:
        cf.note("transcript", "x", role="user")
        cf.note("widget", "show", extra={"id": focus, "src": "flash"})
        cf.note("transcript", "x", role="user")
    monkeypatch.setattr(tb, "_possible_now", lambda w, a: True)
    monkeypatch.setattr(tb, "_card_label", lambda w: w)
    try:
        return tb.target_question(ids)
    finally:
        cf._reset()


def test_the_question_says_which_card_his_last_turn_acted_on(monkeypatch):
    q = _q(monkeypatch, ["youtube", "musica"], "musica")
    assert "His previous turn acted on «musica»" in q["instructions"]
    assert "names a kind of thing" in q["instructions"], "the counterweight is what keeps «next song» on music"


def test_without_a_last_card_the_question_is_unchanged(monkeypatch):
    q = _q(monkeypatch, ["youtube", "musica"], "")
    assert q["instructions"] == tb.TARGET_INSTRUCTIONS
