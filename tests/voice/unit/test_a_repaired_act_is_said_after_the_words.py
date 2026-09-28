"""An order the second pass carried out is SAID after the model's words (demo pass 31, E4, 2026-09-28).

«oh and leave that inworld one as unread» — the model called nothing and said «there's no unread toggle for a mail
message»; the verdict's second pass then marked it unread. Done, and the last thing heard was that it could not be.
The voice cannot unsay what already streamed, so it says what happened after it.
"""
import pathlib

from nucleo.flash import act_repair

_NUCLEO = pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"


def test_words_that_did_not_promise_the_act_get_the_done_line(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    tail = act_repair.after_the_repair("Hmm, that one I can't do — there's no unread toggle.", promised=False)
    assert tail.strip() == "Done."


def test_words_that_promised_it_or_silence_get_nothing():
    assert act_repair.after_the_repair("Marcándolo como no leído.", promised=True) == ""
    assert act_repair.after_the_repair("", promised=False) == ""


def test_the_voice_turn_says_it_right_after_the_second_pass():
    src = _NUCLEO.read_text("utf-8")
    i = src.index("prometió actuar sin tool — la llamada, en una segunda pasada")
    assert "_act_repair.after_the_repair(spoken_text" in src[i:i + 900]
