"""The canvas arbiter reads the turn's PAID verdict first; the word leaves only decide where it is silent (refactor2710-04).

Replayed over the operator's archive, the word leaves vetoed six mutations the brief had ordered — four closes
(`canvas=close`, two of them «close everything») and two data ops whose `screen_action` named exactly that card and
action. A word gate above a paid verdict is what CRIT-K1 forbids. The canvas reporting what it already did (`client`)
and a task's wall opening its own card (`wall:<tid>`) are declared provenances, never judged by words.
"""
from __future__ import annotations

import pytest

from nucleo.acts import canvas_arbiter as arb
from nucleo.acts import canvas_turn as turn

MUTE = "mm, vale"           # words no leaf licenses: only the verdict can


def test_the_verdict_licenses_what_the_words_did_not():
    assert arb.decide("close", "musica", "flash", text=MUTE, verdict={"canvas": ("close", 0.99)}).rule == "verdict-close"
    assert arb.decide("close", "", "flash", text=MUTE, verdict={"canvas": ("close", 0.66)}).allow
    v = arb.decide("data", "youtube", "flash", action="pause", text=MUTE,
                   verdict={"screen_action": ("youtube:pause", 0.98)})
    assert v.allow and v.rule == "verdict-action"
    assert arb.decide("show", "navegador", "flash", text=MUTE,
                      verdict={"canvas": ("neither", 0.98), "catalog_widget": ("navegador", 0.88)}).rule == "verdict-catalog"


def test_a_sure_contrary_verdict_vetoes_and_a_close_order_licenses_no_show():
    assert arb.decide("close", "agenda", "flash", text="cierra la agenda",
                      verdict={"canvas": ("neither", 0.95)}).rule == "verdict-against"
    assert arb.decide("show", "agenda", "flash", text="la agenda",
                      verdict={"canvas": ("close", 0.9)}).rule == "verdict-close-not-show"


def test_a_close_order_that_also_opens_is_two_orders():
    """«close the messages and show me the agenda» closes one card and shows another; a bare close order still
    licenses no show (the bank's v2-567 case, here in the other language)."""
    assert arb.decide("show", "agenda", "flash", text="close the messages and show me the agenda").allow
    assert arb.decide("show", "agenda", "flash", text="cierra la agenda").rule == "show-against-close-order"


def test_an_unsure_or_absent_verdict_leaves_the_words_to_decide():
    assert arb.decide("close", "youtube", "flash", text="cierra el widget de youtube").rule == "close-grammar"
    assert arb.decide("close", "youtube", "flash", text=MUTE, verdict={"canvas": ("close", 0.46)}).rule == "close-drag"


def test_a_report_and_a_wall_are_declared_provenances():
    assert arb.decide("close", "results", "client", text=MUTE).rule == "report"
    v = arb.decide("show", "results::1", "wall:t1", text=MUTE)
    assert v.allow and v.rule == "task-owned" and v.evidence.get("via") == "wall"


@pytest.fixture
def verdicts(monkeypatch):
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append({"kind": kind, "label": label, **(extra or {})}))
    turn._last_turn.update(text="", ts=0.0, credit=True)
    turn._reads.clear()
    return out


def test_the_tap_reads_the_brief_off_its_events_and_the_verdict_event_carries_it(verdicts):
    turn.shadow_tap("brain", "jev read canvas", "", "system",
                   {"question": "canvas", "choice": "close", "confidence": 0.87, "trace": "T19·5b76"})
    turn.shadow_tap("transcript", "🗣", MUTE, "user", None)
    turn.shadow_tap("widget", "close", "", "", {"id": "musica", "src": "flash", "trace": "T19·5b76"})
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["kind"] == "arbiter" and v["label"] == "✅ permitiría · verdict-close", "kind and label keep their shape"
    assert v["verdict"] == {"canvas": {"choice": "close", "confidence": 0.87}} and v["source"] == "flash"


def test_the_catalogue_asked_with_cards_open_licenses_the_show_like_the_bare_one(verdicts):
    """Demo sandbox 2026-11-05, F1: «write me a one page summary of the bitcoin whitepaper, in a document» with the
    monitors sheet minimized. The brief asks the catalogue under `catalog_closed` when cards are open; the document was
    written and its show vetoed («verdict-against», canvas=neither 0.98) because the arbiter read only `catalog_widget`.
    Both keys are the one catalogue answer: the late catalogue licenses the show of the card it names."""
    from nucleo.turn import brief as tb
    turn.shadow_tap("brain", "jev read canvas", "", "system",
                   {"question": tb.CANVAS_KEY, "choice": "neither", "confidence": 0.98, "trace": "T82·94b1"})
    turn.shadow_tap("brain", "jev read catalog_closed", "", "system",
                   {"question": tb.CATALOG_CLOSED_KEY, "choice": "documento", "confidence": 0.90, "trace": "T82·94b1"})
    req = turn.request_for({"trace": "T82·94b1"})
    assert req["verdict"].get(tb.CATALOG_KEY) == ("documento", 0.90), req["verdict"]
    v = arb.decide("show", "documento", "flash", text="write me a one page summary of the bitcoin whitepaper, in a document",
                   verdict=req["verdict"])
    assert v.allow and v.rule == "verdict-catalog", (v.rule, req["verdict"])
    # and from a door that holds the brief handle (`request_of`), the same slot
    class _H(dict):
        pass
    brief = {"_reads": {tb.CANVAS_KEY: ("neither", 0.98), tb.CATALOG_CLOSED_KEY: ("documento", 0.90)}}
    import nucleo.turn.brief as _tbm
    real_read = _tbm.read
    try:
        _tbm.read = lambda h, key, fb, min_confidence=None: ((h["_reads"][key][0], {"confidence": h["_reads"][key][1]})
                                                             if key in h["_reads"] else (fb, None))
        req2 = turn.request_of(brief, text="write me a summary in a document")
    finally:
        _tbm.read = real_read
    assert req2["verdict"].get(tb.CATALOG_KEY) == ("documento", 0.90), req2["verdict"]
