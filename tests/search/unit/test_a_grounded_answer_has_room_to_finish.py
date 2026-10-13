"""A grounded answer has room to finish: thinking off where it can be, and a budget above what it spends.

Use case `quick-fact-opening-hours` ES (2026-10-14): Gemini's answer arrived cut mid-word («…y los domingos y
fest») because `gemini-2.5-flash` thinks by default and its thought tokens are charged to `maxOutputTokens`,
which was 300. The recorded one-fact fixture already spent 292 of those 300.
"""
from __future__ import annotations

import json
from pathlib import Path

from search.providers import gemini, gemini_budget

FIX = Path(__file__).resolve().parents[1] / "fixtures"


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _sent_body(monkeypatch, model: str) -> dict:
    import httpx
    seen: dict = {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            seen["body"] = json
            return _Resp(__import__("json").loads((FIX / "gemini_grounding.json").read_text(encoding="utf-8")))

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_SEARCH_MODEL", model)
    from nucleo import energy_meter
    monkeypatch.setattr(energy_meter, "report_search_usage", lambda **kw: None)
    gemini.search("¿A qué hora abre mañana el Prado y cuánto cuesta la entrada?")
    return seen["body"]


def test_the_default_model_is_asked_not_to_think(monkeypatch):
    cfg = _sent_body(monkeypatch, "gemini-2.5-flash")["generationConfig"]
    assert cfg.get("thinkingConfig") == {"thinkingBudget": 0}
    assert cfg["maxOutputTokens"] >= 1024


def test_a_model_that_cannot_skip_thinking_keeps_its_default_and_the_room(monkeypatch):
    cfg = _sent_body(monkeypatch, "gemini-2.5-pro")["generationConfig"]
    assert "thinkingConfig" not in cfg, "a zero budget on 2.5 Pro is a 400: the chain would lose Gemini entirely"
    assert cfg["maxOutputTokens"] >= 1024


def test_the_budget_is_well_above_what_the_recorded_answer_spent():
    use = json.loads((FIX / "gemini_grounding.json").read_text(encoding="utf-8"))["usageMetadata"]
    spent = use["thoughtsTokenCount"] + use["candidatesTokenCount"]
    assert gemini_budget.MAX_OUTPUT_TOKENS >= 3 * spent, (spent, gemini_budget.MAX_OUTPUT_TOKENS)
