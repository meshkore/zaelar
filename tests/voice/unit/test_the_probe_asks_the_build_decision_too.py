"""The text probe decides «build a new widget or show one we have» the way the voice turn does (V2-778 F2-22, 2026-10-02).

V2-750 moved the voice turn's create guard from the bare grammar (`router_guards.looks_like_create_widget`) to
`build_decision.decide`, which lets the turn's verdict VETO a create over a card we already have. The probe kept the
bare grammar, so «vamos a hacer una cosa, ábreme el widget de vídeo» still escalated to the generator there — and the
bank of brain cases runs on the probe, so the bank measured the bug V2-750 had fixed. Found by the voice/probe import
ratchet (`build_decision` was listed as an «owed» voice-only module).

Run: .venv/bin/pytest tests/voice/unit/test_the_probe_asks_the_build_decision_too.py
"""
from __future__ import annotations

import asyncio
import threading

from nucleo.flash import build_decision as _bd
from nucleo.flash import probe_decide as _pd
from nucleo.flash import router_guards as _rg
from nucleo.flash import turn_brief as _tb

HIS_WORDS = ("Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, "
             "preséntame un catálogo de vídeos sobre el Apolo once.")


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


class _Sess:
    window: list = []
    last_action = ""


def _action(text, brief):
    calls = [{"name": "show_widget", "args": {"widget_id": "youtube"}}]
    blk = asyncio.run(_pd.name_the_action(_hard=None, _router=_rg, _tbrief=brief, _vault_gate=None, ingest=None,
                                          names={"show_widget"}, sess=_Sess(), tags=[], text=text, tool_calls=calls))
    return blk.get("action", "")


def test_the_grammar_alone_would_build():
    assert _rg.looks_like_create_widget(HIS_WORDS), "the sentence must still trip the grammar, or this tests nothing"


def test_a_verdict_naming_a_card_we_have_vetoes_the_build_in_the_probe():
    brief = _brief({_tb.CATALOG_KEY: ("youtube", 0.98), _bd.BUILD_KEY: ("use_existing", 0.78)})
    assert _action(HIS_WORDS, brief) != "escalate", "the probe built a duplicate widget the verdict had vetoed"


def test_a_real_create_still_escalates_in_the_probe():
    brief = _brief({_tb.CATALOG_KEY: ("none", 0.97), _bd.BUILD_KEY: ("build_new", 0.81)})
    assert _action("créame un widget de ajedrez", brief) == "escalate"
