"""The errand's KIND is the turn brief's verdict, never a reading of its words (V2-851 F4, audit P0-4).

`nucleo/request/kind.py` decided web/code/generic with six regexes and a chain of site and money word tables. Now the
kind is one more declared question of the brief, carried by the portal in the errand's context (`errand_kind`) and
read at the licence: `web` → a browser, `build_card`/`change_card` → the card generator behind CRIT-C4's gate, the rest
and an unsure verdict → `generic`. The same request with another verdict is another kind, and no regex is left in the
file (the disarm: a regex reintroduced turns `test_no_word_reader_is_left` red).
"""
from __future__ import annotations

import inspect

from nucleo.request import kind as K
from nucleo.turn import brief as tb

SAME_WORDS = "Rediseña el widget de vídeo y búscame entradas para el concierto del sábado"


def _v(choice: str, conf: float = 0.95) -> dict:
    return {"choice": choice, "confidence": conf}


def test_the_kind_follows_the_verdict_not_the_words():
    assert K.kind_of(_v(K.WEB)) == "web"
    assert K.kind_of(_v(K.BUILD)) == K.kind_of(_v(K.CHANGE)) == "code"
    assert K.kind_of(_v(K.GENERIC)) == "generic"
    assert K.code_change(_v(K.BUILD)) == "create" and K.code_change(_v(K.CHANGE)) == "modify"
    assert K.code_change(_v(K.WEB)) == ""


def test_an_unsure_or_missing_verdict_is_generic():
    assert K.kind_of(None) == K.kind_of(_v(K.WEB, 0.3)) == K.kind_of(_v("teleport")) == "generic"
    assert K.code_change(_v(K.BUILD, 0.3)) == ""


def test_the_question_is_declared_and_the_brief_asks_it():
    q = K.question()
    assert set(q["criteria"]) == {K.WEB, K.BUILD, K.CHANGE, K.GENERIC}
    assert K.KEY in tb.build(SAME_WORDS)


def test_the_portal_carries_the_turn_verdict(monkeypatch):
    monkeypatch.setattr(K, "verdict", lambda b: _v(K.CHANGE))
    ctx: dict = {}
    K.carry(ctx)
    assert ctx[K.KEY] == _v(K.CHANGE)
    kept = {K.KEY: _v(K.WEB), "errand_class": {"choice": "none", "confidence": 1.0}}
    K.carry(kept)
    assert kept[K.KEY] == _v(K.WEB), "a commission that already carries its verdict is not re-read"


def test_no_word_reader_is_left():
    src = inspect.getsource(K)
    assert "re.compile" not in src and "import re" not in src
