"""search/providers/gemini_budget.py — the output budget of a grounded answer, and the answer it cut (quick-fact).

Measured on use case `quick-fact-opening-hours` (ES, sweep 2026-10-14 00:23): «¿A qué hora abre mañana el Museo
del Prado y cuánto cuesta la entrada general?» came back from Gemini as

    «El Museo del Prado abre de lunes a sábado de 10:00 a 20:00 h, y los domingos y fest»

— an HTTP 200, cut mid-word, no price. `gemini-2.5-flash` THINKS by default and its thought tokens are charged to
`maxOutputTokens`: the recorded fixture of the one-fact question already spent 184 thought + 108 answer tokens of
the 300 allowed, so a two-fact question ran out before the second fact. The turn read the stump as the answer,
told the operator the search «only brought the hours, cut», offered the browser, and the case's forbidden signal
(a Brain Worker with a browser for a fact one search answers) followed from the «yes».

Two things live here:
  · `generation_config(model)` — thinking OFF on the models that accept a zero budget (2.5 Flash / Flash-Lite;
    2.5 Pro cannot turn it off and a zero there is a 400), and room for three sentences in any case.
  · `was_cut(candidate)` — the provider's own word that it stopped on the budget. A cut answer is not an answer:
    the provider drops it so the chain asks the next index instead of handing the stump to the reader.
"""
from __future__ import annotations

#: Room for the 1-3 sentences the instruction asks for, plus thought tokens on a model that cannot skip them.
MAX_OUTPUT_TOKENS = 1024


def thinking_can_be_off(model: str) -> bool:
    """Only the 2.5 Flash family accepts `thinkingBudget: 0`; anything else keeps the provider's default."""
    m = (model or "").lower()
    return m.startswith("gemini-2.5-flash")


def generation_config(model: str) -> dict:
    cfg: dict = {"maxOutputTokens": MAX_OUTPUT_TOKENS}
    if thinking_can_be_off(model):
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    return cfg


def was_cut(candidate: dict) -> bool:
    """True when the candidate stopped because the output budget ran out (`finishReason: MAX_TOKENS`)."""
    return str((candidate or {}).get("finishReason") or "").upper() == "MAX_TOKENS"
