"""A card read answers the OPERATOR's words — never the model's third-person look-up query (V2-831 T-19 R3, audit A14).

Demo pass 8, R3: «find me five days in her vacation where i'm free» → the model read the agenda with the query
«What meetings… does Rowan have between…», and the read's spoken answer echoed it: «Rowan has nothing on the calendar
during Quinn's vacation…». The first fix added a sentence to the prompt («address him in the second person»), a rail on
judgement. The mechanism is the FRAME: the composer answers his words, and the model's query is shown only as what was
looked up — so nothing in the prompt names him in the third person as the thing to answer.

The prompt's instructions are language data (`widget_read.*` in the voice pack — English source, Spanish preset, any
other language generated at init), so the composer reads them in his language.

Disarm: present the model's query as the question (before his words) → red; build the instructions from a literal in
one language → red for the other.
"""
from __future__ import annotations

import pytest

QUERY = "What meetings does Rowan have between 2026-12-20 and 2027-01-04?"
HIS = {"en": "find me five days in her vacation where i'm free", "es": "búscame cinco días libres en sus vacaciones"}


@pytest.mark.parametrize("code", ["en", "es"])
def test_the_read_composer_answers_his_words_in_his_language(monkeypatch, code):
    from i18n import langs
    from nucleo.flash import widget_read
    monkeypatch.setattr(langs, "current_code", lambda: code)
    W = langs.words("widget_read", code=code)
    sys2 = widget_read.compose_system("", HIS[code], "agenda", QUERY, "(no entries)", answered=True)
    his_line, query_line = f"{W['his_words']}: {HIS[code]}", f"{W['looked_up']}: {QUERY}"
    assert his_line in sys2 and query_line in sys2
    assert sys2.index(his_line) < sys2.index(query_line), "the frame is his words; the query is only what was looked up"
    assert W["task"].format(name=widget_read.title("agenda"), wid="agenda") in sys2
    other = langs.words("widget_read", code="es" if code == "en" else "en")
    assert other["task"].split("«")[0] not in sys2, "the instructions came in another language than his"


def test_no_behaviour_sentence_about_whom_to_address_rides_the_prompt():
    from i18n import langs
    for code in ("en", "es"):
        text = " ".join(str(v) for v in langs.words("widget_read", code=code).values()).lower()
        assert "second person" not in text and "segunda persona" not in text
