"""A courtesy question at the end of a list step's reply does not hold the step (node 2.188).

Demo pass 65 (2026-09-30): the INIT's «Your name is Johnny…» step replied «Got it, Johnny here. What do you
need?», and the list closed «26 of 27 done. I need you to clarify: Got it, Johnny here. What do you need?». The
judge (`reply_needs_him`, one Jev question) said `done` but at 0.56-0.58, under its 0.7 floor, because nothing in
its criterion named an acknowledgement that introduces itself or «what do you need?». Measured after the change,
three times each: that reply 0.95-0.97 `done`; «what time should I book it for?», «which Ethan do you mean?» and
«shall I go ahead and buy it?» all `needs_answer` at 0.99-1.00.
"""
from nucleo.batch import runner


def test_the_done_criterion_names_the_courtesy_forms_it_must_release():
    done = runner._NEEDS_CRITERIA["done"]
    for phrase in ("introducing itself", "what do you need?", "anything else?"):
        assert phrase in done, phrase


def test_a_real_question_back_still_holds_the_step():
    ask = runner._NEEDS_CRITERIA["needs_answer"]
    assert "which one" in ask and "missing detail" in ask and "permission" in ask
