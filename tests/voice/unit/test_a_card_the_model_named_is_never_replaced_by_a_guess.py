"""A word-level guess never replaces the card the model named, and a second pass never mints a web address
(V2-807 T-06).

Measured, one chain: «I don't see it — where is it? Open it» → the model called `show_widget(documento)`, which was
right. The deictic guard read «it», walked back to his previous line — a complaint that NAMED the browser — and the
show became the browser. A second pass then «completed» it with `navegador:open https://docs.google.com` (the
document turned into Google Docs, a sign-in page on his screen), and on the next turn — «why are you opening a
browser? I asked for the draft» — a promise backstop re-opened the browser from the noun in his complaint.

The class: a guess FILLS a missing target, never replaces a present one; a second pass completes the card the turn
chose and never mints an address nobody said; the show grammar proposes and a sure verdict decides.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import show_target as ST

SAID = "Vale, pero no lo veo, ¿Dónde está? Ábrelo"
WINDOW = [{"role": "user", "content": "¿Por qué has abierto un nuevo navegador?"}]


def _guess(*_a):
    return "navegador"            # what the deictic walk-back produced, measured


def _brief(canvas, conf=0.96):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": {"canvas": {"choice": canvas, "confidence": conf}}}


# ── 1. the card the model named wins ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model_id", ["documento", "results::ab12-1"])
def test_the_model_named_card_beats_the_deictic_guess(model_id):
    res, _o, _r = ST.resolve_show(model_id, SAID, WINDOW, "", _guess)
    assert res["match"] == model_id


def test_the_guess_still_fills_a_missing_target():
    res, _o, _r = ST.resolve_show("", SAID, WINDOW, "", _guess)
    assert res["match"] == "navegador"


def test_a_garbled_id_is_a_missing_target():
    assert ST.model_named("no-such-card") == ""
    assert ST.named_or_guess("no-such-card", lambda: "navegador") == "navegador"
    assert ST.named_or_guess("documento", lambda: "navegador") == "documento"
    assert ST.named_or_guess("results::ab12-1", lambda: "navegador", bases_only=True) == "navegador"


def test_disarmed_a_guard_that_runs_first_turns_the_document_into_the_browser(monkeypatch):
    """RED proof: with no card read as named, the guess wins again — the tests above measure `model_named`."""
    monkeypatch.setattr(ST, "model_named", lambda wid: "")
    res, _o, _r = ST.resolve_show("documento", SAID, WINDOW, "", _guess)
    assert res["match"] == "navegador", "the disarm did not land"
    monkeypatch.undo()
    assert ST.resolve_show("documento", SAID, WINDOW, "", _guess)[0]["match"] == "documento"   # green again


# ── 2. a second pass never mints an address ───────────────────────────────────────────────────────────────────────

def _emit_into(events):
    return lambda kind, action, text=None, role=None, extra=None: events.append((action, extra))


class _Router:
    @staticmethod
    def looks_like_show_strict(text):
        return True                # the grammar fires on «abres … navegador»


COMPLAINTS = ["¿Por qué me abres un navegador? Te he pedido el borrador",
              "Why are you opening a browser? I asked for the draft",
              "为什么打开浏览器？我要的是草稿"]


@pytest.mark.parametrize("said", COMPLAINTS)
def test_a_sure_non_show_verdict_overrules_the_show_grammar(said):
    assert ST.show_proposed(_brief("neither"), _Router, said) is False


def test_no_verdict_leaves_the_grammar_as_today():
    assert ST.show_proposed(None, _Router, COMPLAINTS[0]) is True
    assert ST.show_proposed(_brief("neither", conf=0.2), _Router, COMPLAINTS[0]) is True


def test_disarmed_a_verdict_nobody_reads_reopens_the_browser(monkeypatch):
    monkeypatch.setattr(ST, "verdict_denies_show", lambda brief: False)
    assert ST.show_proposed(_brief("neither"), _Router, COMPLAINTS[0]) is True, "the disarm did not land"
    monkeypatch.undo()
    assert ST.show_proposed(_brief("neither"), _Router, COMPLAINTS[0]) is False   # green again
