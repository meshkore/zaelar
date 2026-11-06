"""A sure close the names verdict would stop first asks Jev which cards ON SCREEN he names to close (demo sandbox
2026-10-29, pass 2, C6; V2-831 T-19 R4c).

«close the calendar and the messages», with the agenda open and the messages not. The brief read canvas=close 1.00,
screen_action=none 0.51 and names_a_card=elsewhere 0.80, even with the mixed criterion of #101. The model called
nothing and said «— done, both closed». Every close reader asked `names_elsewhere` and stood down, and the agenda
stayed open.

  · `brief_screen.names_elsewhere`: when it would stop a sure canvas close, ONE closed question
    (`named_to_close`, `jev.select_many` over the labels of the cards on screen, «which of these does he name to
    close») decides. The picked cards close (`card_close.run_gesture`); none picked → the verdict stands. Asked
    only on that branch, cached on the handle. No word reading.

Disarm: make `named_to_close` answer [] without asking. The reader and real-turn tests go red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import brief as tb, brief_screen

MIXED = {"en": ("close the calendar and the messages", "— done, both closed."),
         "es": ("cierra la agenda y los mensajes", "— hecho, cerradas las dos.")}
ALIAS = {"en": ("close the diary", "Done."), "es": ("cierra el calendario", "Hecho.")}
PASS2 = {"canvas": ["close", 1.0], "screen_action": ["none", 0.51], "names_a_card": ["elsewhere", 0.80],
         "wants_words": ["act", 1.0], "escalate_or_inline": ["handle_inline", 1.0], "request_type": ["order", 0.9]}


def _handle(judged, open_ids, names=("elsewhere", 0.9), canvas=("close", 1.0)):
    ev = threading.Event()
    ev.set()
    res = {tb.NAMES_KEY: names, tb.CANVAS_KEY: canvas}
    return {"event": ev, "turn_id": "t", "open_ids": list(open_ids), "judged": judged,
            "result": {k: {"choice": c, "confidence": p, "probs": {c: p}} for k, (c, p) in res.items()}}


@pytest.fixture
def select(monkeypatch):
    """Jev's closed close question, stubbed as the bank answers it (`harness.close_pick_answer`); calls recorded."""
    from nucleo import jev
    from tests.platform import turn_harness as harness
    st = {"picks": [], "calls": []}

    def fake(state, questions, **k):
        st["calls"].append((state, [q["instructions"] for q in questions.values()], k.get("question_id")))
        return harness.close_pick_answer(st["picks"])(state, questions, **k)
    monkeypatch.setattr(jev, "choose_many_sync", fake)
    return st


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_close_question_picks_the_card_on_screen_and_the_verdict_yields(select, lang):
    select["picks"] = ["agenda"]
    h = _handle(MIXED[lang][0], ["agenda", "results"])
    assert brief_screen.names_elsewhere(h) is False and brief_screen.names_elsewhere(h, against_a_call=True) is False
    assert len(select["calls"]) == 1, "one question per turn, cached on the handle"
    state, instructions, qid = select["calls"][0]
    assert qid == "close_pick" and MIXED[lang][0] in state and len(instructions) == 2
    assert brief_screen.named_to_close(h) == ["agenda"], "a «yes» split over two grades (named 0.75, margin 0.16) still picks"


def test_nothing_picked_the_verdict_stands(select):
    assert brief_screen.names_elsewhere(_handle("close the weekend", ["agenda", "results"])) is True
    assert len(select["calls"]) == 1


def test_asked_only_where_the_verdict_would_stop_a_sure_close(select):
    brief_screen.names_elsewhere(_handle(MIXED["en"][0], ["agenda"], names=("on_screen", 0.9)))
    brief_screen.names_elsewhere(_handle(MIXED["en"][0], ["agenda"], canvas=("neither", 0.9)))
    assert select["calls"] == [] and not brief_screen.named_to_close(_handle("x", ["agenda"], canvas=("neither", 0.9)))


# ── the real headless turn (the bank's recorded `select` is Jev's answer to the closed question) ──────────────
def _turn(lang, phrase, say, open_ids, picks=()):
    from tests.platform import turn_harness as harness
    case = {"id": f"r4c-{lang}", "lang": lang, "phrase": phrase, "source": "demo sandbox 2026-10-29 pass 2 C6",
            "screen": {"open": list(open_ids)}, "model": {"say": say, "tools": []}, "brief": dict(PASS2),
            "select": list(picks), "expect": "close agenda", "forbid": ["data-op"]}
    return harness.run_case(case)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_named_card_on_screen_closes_and_the_absent_one_is_not_used(lang):
    out = _turn(lang, *MIXED[lang], ["agenda", "results"], picks=["agenda"])
    assert out.decision == "close agenda", (out.decision, out.also, out.reply)
    assert "close mensajeria" not in out.all_decisions and not [d for d in out.all_decisions if d.startswith("data-op")]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_an_alias_reaches_its_card_through_the_question(lang):
    out = _turn(lang, *ALIAS[lang], ["agenda", "results"], picks=["agenda"])
    assert out.decision == "close agenda", (out.decision, out.also, out.reply)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_both_named_cards_on_screen_both_close(lang):
    out = _turn(lang, *MIXED[lang], ["agenda", "mensajeria"], picks=["agenda", "mensajeria"])
    assert {"close agenda", "close mensajeria"} <= set(out.all_decisions), out.all_decisions


def test_nothing_named_on_screen_closes_nothing():
    out = _turn("en", "close the weekend", "Done.", ["agenda", "results"])
    assert out.decision == "talk" and not any(d.startswith("close") for d in out.all_decisions), out.all_decisions
