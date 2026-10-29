"""Two closes that read less than he said (demo sandbox 2026-10-29, pass 4; V2-831 T-19 R4e).

C6 «close the calendar and the messages». The close question of #112 WAS asked. It went through `select_many`, whose
three FIT grades split a «yes» into strong + partial: the agenda read strong 0.44 · partial 0.31 · no 0.25 and was
dropped at margin 0.16, so nothing was picked, the names verdict held and nothing closed. The question is now one
closed yes/no per card on screen (`brief_screen.named_to_close`, one `choose_many_sync` trip), read by the mass Jev
gives «named» at the licence.

Z2 «clear everything off the screen» left the Images card open. The hard interrupt read a close-all (the canvas noun
«everything»), but its scope reader (`close_scope`, T-02) asked only whether a quantifier GOVERNS a card word, and
«everything» governs «off». The spare then kept the card in use. A closing clause that carries a quantifier AND a
canvas noun is a total (`interrupt_grammar._closes_the_whole_canvas`), with no new word or regex: the two existing
tables, read together.

Disarm: read the close question's verdict by its margin again, or drop the «quantifier and canvas noun» reading from
the scope. The real-turn tests go red.
"""
from __future__ import annotations

import pytest

from tests.brain import harness

C6 = {"en": ("close the calendar and the messages", "Okay… calendar's closed."),
      "es": ("cierra la agenda y los mensajes", "Vale, agenda cerrada.")}
PASS4 = {"canvas": ["close", 1.0], "screen_action": ["none", 0.49], "names_a_card": ["elsewhere", 0.89],
         "wants_words": ["act", 1.0], "escalate_or_inline": ["handle_inline", 1.0], "request_type": ["order", 0.9]}


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_yes_split_over_two_grades_still_closes_the_card(lang):
    """The recorded answer is pass 4's: named 0.75 for the agenda at margin 0.16 (`harness.close_pick_answer`)."""
    phrase, say = C6[lang]
    out = harness.run_case({"id": f"r4e-c6-{lang}", "lang": lang, "phrase": phrase, "source": "pass 4 C6",
                            "screen": {"open": ["results", "agenda"]}, "model": {"say": say, "tools": []},
                            "brief": dict(PASS4), "select": ["agenda"], "expect": "close agenda", "forbid": []})
    assert out.decision == "close agenda", (out.decision, out.also, out.reply)
    assert "close results" not in out.all_decisions


@pytest.fixture
def images_in_use(monkeypatch):
    from nucleo.flash import bulk_close
    monkeypatch.setattr(bulk_close, "working_card",
                        lambda open_ids, within_s=300.0: next((o for o in open_ids if o.startswith("imagenes")), ""))


def _clear(lang, phrase):
    return harness.run_case({"id": f"r4e-z2-{lang}", "lang": lang, "phrase": phrase, "source": "pass 4 Z2",
                             "screen": {"open": ["documento", "imagenes"]}, "model": {"say": "Done.", "tools": []},
                             "expect": "close all", "forbid": []})


@pytest.mark.parametrize("lang,phrase", [("en", "clear everything off the screen"),
                                         ("es", "cierra todo lo que hay en pantalla")])
def test_a_whole_canvas_total_closes_the_card_in_use_too(images_in_use, lang, phrase):
    out = _clear(lang, phrase)
    assert out.decision == "close all", (out.decision, out.tags, out.reply)


@pytest.mark.parametrize("lang,phrase", [("en", "close the widgets"), ("es", "cierra las ventanas que no uses")])
def test_a_close_of_the_cards_with_no_total_still_spares_the_one_in_use(images_in_use, lang, phrase):
    out = _clear(lang, phrase)
    assert out.decision == "close documento" and "close imagenes" not in out.all_decisions, (out.decision, out.also)
