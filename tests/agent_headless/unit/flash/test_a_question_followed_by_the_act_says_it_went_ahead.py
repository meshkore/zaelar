"""A verdict-completed act the model's words only ASKED about is followed by the went-ahead line (passes 76/90, T509).

«Compare them visually.» — the model asked «Which view do you want them in, side by side?»; the verdict set
`layout: compare`, the sheet changed, and the last thing heard was the question.
"""
from nucleo.flash import act_repair as AR


def test_a_question_then_a_completed_view_says_it_went_ahead(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en", raising=False)
    tail = AR.after_the_completion("Which view do you want them in, side by side?", "results", "layout")
    assert tail.strip() and "?" not in tail


def test_words_that_did_not_ask_need_nothing():
    assert AR.after_the_completion("Putting them side by side now.", "results", "layout") == ""


def test_an_act_whose_answer_comes_from_its_data_adds_nothing():
    """find_free carries output.answer: its answer is composed from the data (after_the_repair's rule)."""
    assert AR.after_the_completion("Want me to check tomorrow afternoon?", "agenda", "find_free") == ""
