"""V2-834 T26 — an answer composed from a data-op's rows reads «those days» against what he said just before.

what-does-my-week-look-like__us: «dentist on November 12, dinner with Laura two days later» → «Done.» → «so what do I
have on those days?» ran `agenda.show_day 2026-11-12`, and the answer pass, shown only his question and that day's
rows, said the dentist and nothing else: the second day lived in the previous exchange, which it never saw.

Disarm: drop `before=` from `op_answer_system` (or make `prior_line.exchange` return "") and this goes red.
"""
from nucleo.flash import prior_line, widget_read

WINDOW = [{"role": "user", "content": "Put two things down: dentist on November 12, and dinner with Laura two days later"},
          {"role": "assistant", "content": "Done."},
          {"role": "user", "content": "so what do I have on those days?"}]


def test_the_previous_exchange_is_his_line_and_our_reply():
    got = prior_line.exchange(WINDOW, "so what do I have on those days?")
    assert "dinner with Laura two days later" in got and "Done." in got
    assert "those days" not in got, "this turn's own words are not what came before"
    assert prior_line.exchange([], "x") == ""


def test_the_answer_pass_sees_what_his_words_point_at():
    before = prior_line.exchange(WINDOW, "so what do I have on those days?")
    sysm = widget_read.op_answer_system("", "so what do I have on those days?", "agenda",
                                        {"day": "2026-11-12", "items": ["Dentist 09:30"]}, [("agenda", "show_day")],
                                        before=before)
    assert "dinner with Laura two days later" in sysm
