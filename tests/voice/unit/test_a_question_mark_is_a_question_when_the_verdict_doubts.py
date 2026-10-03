"""With both readings unsure, the operator's own question mark makes it a question (node 2.191).

Demo pass 66, R2 (2026-09-30): «and when does anna's vacation start? show me in the calendar» → `agenda:show_day
{day: 2026-12-20}` and «Done.» — the date was never said. `request_type` read question at 0.42 and `wants_words` tell at
0.02, both unsure, so `question_left_to_a_lens` never asked the card. Punctuation is language-free evidence.
"""
from nucleo.flash import card_commission as cc
from nucleo.flash import turn_brief as tb

OPS = [{"widget_id": "agenda", "action": "show_day"}]


def _unsure(monkeypatch):
    """The REAL shape of an unsure reading (`jev.read`): the fallback, and an info that says it was not used. The
    first version of this test stubbed `(default, None)` — what only an ABSENT verdict returns — and stayed green
    while the product never fired (pass 92, R2)."""
    def _read(brief, key, default="", **k):
        if key == tb.REQUEST_KEY:
            return default, {"choice": "answer", "confidence": 0.23, "used": False}
        if key == tb.WORDS_KEY:
            return default, {"choice": "tell", "confidence": 0.20, "used": False}
        return default, None
    monkeypatch.setattr(tb, "read", _read)
    from nucleo.flash import widget_read as wr
    monkeypatch.setattr(wr, "can_answer", lambda wid: True)


def test_a_question_mark_with_an_unsure_verdict_reads_the_card(monkeypatch):
    _unsure(monkeypatch)
    got = cc.question_left_to_a_lens({"x": 1}, ops=OPS, acted={},
                                     operator_text="and when does anna's vacation start? show me in the calendar")
    assert got == "agenda"


def test_no_question_mark_and_an_unsure_verdict_reads_nothing(monkeypatch):
    _unsure(monkeypatch)
    assert cc.question_left_to_a_lens({"x": 1}, ops=OPS, acted={}, operator_text="show me the calendar") == ""


def test_a_sure_order_is_not_overruled_by_a_question_mark(monkeypatch):
    monkeypatch.setattr(tb, "read", lambda brief, key, default="", **k: ("order", {"used": True}) if key == tb.REQUEST_KEY
                        else ("act", {"used": True}) if key == tb.WORDS_KEY else (default, None))
    assert cc.question_left_to_a_lens({"x": 1}, ops=OPS, acted={}, operator_text="can you show me the calendar?") == ""


def test_the_real_reader_shape_for_unsure_is_what_the_rule_reads(monkeypatch):
    """Pin the reader itself, so the stub above cannot drift from it again: an unsure verdict is NOT None."""
    from nucleo import jev
    handle = {"x": 1}
    monkeypatch.setattr(jev, "peek", lambda h: {tb.REQUEST_KEY: {"choice": "answer", "confidence": 0.23}})
    monkeypatch.setattr(jev, "_emit_read", lambda *a, **k: None)
    choice, info = jev.read(handle, tb.REQUEST_KEY, "")
    assert choice == "" and info is not None and info.get("used") is False
