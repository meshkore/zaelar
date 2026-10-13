"""A cut answer is not an answer: Gemini's `MAX_TOKENS` stump is dropped and the fact chain asks the next index.

Use case `quick-fact-opening-hours` ES (2026-10-14): «El Museo del Prado abre de lunes a sábado de 10:00 a
20:00 h, y los domingos y fest» was handed to the reader as THE answer; the turn said the search brought «el
horario cortado y nada del precio», offered the browser, and a Brain Worker was spawned for a fact.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import web
from search.providers import gemini

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def _cut() -> dict:
    return json.loads((FIX / "gemini_grounding_cut.json").read_text(encoding="utf-8"))


def test_the_stump_is_dropped_and_said_to_be_cut():
    out = gemini.parse(_cut(), 5)
    assert out == {"answer": "", "results": [], "cut": True}


def test_a_finished_answer_is_still_read():
    out = gemini.parse(json.loads((FIX / "gemini_grounding.json").read_text(encoding="utf-8")), 5)
    assert out["answer"] and "cut" not in out


@pytest.fixture
def two_indexes(monkeypatch):
    for k in ("PERPLEXITY_API_KEY", "PPLX_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_KEY", "BRAVE_API_KEY",
              "OPENAI_API_KEY", "WEBSEARCH_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    monkeypatch.setenv("BROWSER_SEARCH", "0")
    web._recent.clear()


def test_the_chain_moves_on_to_the_next_index(two_indexes, monkeypatch):
    def gemini_cut(q, k):
        p = gemini.parse(_cut(), k)
        return {"query": q, "answer": p["answer"], "results": p["results"], "source": "gemini"}

    rows = [{"title": "Horarios y tarifas — Museo del Prado", "snippet": "De lunes a sábado de 10 a 20 h. "
             "Entrada general: 15 €.", "url": "https://www.museodelprado.es/visita-el-museo"}]
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "gemini": gemini_cut,
                                           "zai": lambda q, k: {"query": q, "answer": "", "results": rows,
                                                                "source": "zai"}})
    res = web.search("Museo del Prado horario y precio entrada general")
    assert res["source"] == "zai" and "15 €" in web.format_results(res)
    assert "fest" not in web.format_results(res), "the stump never reaches the reader"
