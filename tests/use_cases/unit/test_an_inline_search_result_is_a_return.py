"""An inline web-search result is a RETURN, not a bare query (V2-781 T516, 2026-10-03).

Measured on `find-a-future-release-and-remind-me__us` and `quick-fact-opening-hours__us`: both judged FAIL for a
date / an opening hour «with no backing — N queries, 0 returns». The sandbox held the inline probe search as ONE
event, label «🔎 resultados web», the query in `text` and what came back in `evidence.items` (paramountplus.com:
«premieres Oct. 30, 2026»). `search_returns` only counted rows labelled «↩», so every sourced inline fact was
filed as a query nobody answered, and the judge read that as invention.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import verify

ROW = {"i": 14, "kind": "search", "label": "🔎 resultados web", "text": "Dexter new season premiere date fall 2026",
       "role": "system", "source": "ddg", "n": 5, "src": "probe",
       "evidence": {"items": [{"t": "Dexter®: Resurrection Season 2: Everything You Need To Know",
                               "u": "https://www.paramountplus.com/sneak-peak/dexter-resurrection-season-2",
                               "s": "Dexter®: Resurrection Season 2 premieres Oct. 30, 2026, on Paramount+."}]}}


def _db(tmp_path, rows):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (kind TEXT, label TEXT, payload TEXT, ts_ms INTEGER, topic TEXT)")
    for i, r in enumerate(rows):
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", ("search", r["label"], json.dumps(r), 1000 + i, ""))
    con.commit()
    con.close()
    return p


def test_the_inline_row_counts_as_a_query_with_its_return(tmp_path):
    got = verify.search_returns(_db(tmp_path, [ROW]))
    assert got["queries"] == 1 and got["returns"] == 1, got
    assert "paramountplus.com" in got["sample"][0] and "Oct. 30, 2026" in got["sample"][0]


def test_a_query_with_nothing_back_is_still_a_bare_query(tmp_path):
    empty = dict(ROW, evidence={"items": []}, n=0)
    got = verify.search_returns(_db(tmp_path, [empty]))
    assert got["queries"] == 1 and got["returns"] == 0, got


# V2-834 T02 (2026-11-02, `quick-fact-opening-hours`): the price came back in the THIRD item; the judge got a
# 140-char sample holding only the hours and filed «20 €» as an invented figure. Every item reaches the judge.
PRADO = dict(ROW, text="Museo del Prado horario apertura y precio entrada general", evidence={"items": [
    {"t": "Museo Nacional del Prado", "u": "https://www.museodelprado.es", "s": "Horario: de lunes a sábado de "
     "10:00 a 20:00 h; domingos y festivos de 10:00 a 19:00 h. " * 3},
    {"t": "Visita el Prado", "u": "https://example.org/a", "s": "Planifica tu visita al museo con antelación."},
    {"t": "¿Cuánto cuestan las entradas?", "u": "https://example.org/b",
     "s": "La entrada general para el Museo del Prado cuesta alrededor de 20 €."}]})


def test_every_inline_item_reaches_the_judge(tmp_path):
    from tests.use_cases.e2e.agent import judge
    got = verify.search_returns(_db(tmp_path, [PRADO]))
    assert any("20 €" in ev for ev in got["inline_evidence"]), got["inline_evidence"]
    assert "20 €" not in got["sample"][0]          # the old sample alone never carried it
    facts = judge.mechanism_facts({"search_returns": got})
    assert "20 €" in facts and "NO es inventada" in facts, facts


def test_the_providers_answer_is_evidence_and_backs_its_figures(tmp_path):
    """V2-834 T30 — quick-fact-opening-hours (ES, 08:30): the provider's `answer` said «10:00 a 20:00 … 15 euros»; the
    harness read only the link titles, and the judge called «15 euros» a market figure with no backing."""
    row = dict(ROW, evidence={"items": [{"t": "Horarios y precios - Museo Nacional del Prado", "u": "https://x"}],
                              "answer": "Abre de 10:00 a 20:00 horas. La entrada general cuesta 15 euros."})
    got = verify.search_returns(_db(tmp_path, [row]))
    assert any("15 euros" in ev for ev in got["inline_evidence"])
    said = [{"who": "zaelar", "text": "Abre a las 10:00 y la entrada general cuesta 15 euros.", "at": 5}]
    assert verify.market_claims_before_delivery(said, {}, {}, [], got["inline_evidence"])["n"] == 0
    assert verify.market_claims_before_delivery(said, {}, {}, [], [])["n"] == 1, "unsourced, it is still flagged"


def test_an_hour_in_the_evidence_does_not_back_a_price():
    """S1 audit H16: the evidence seeded EVERY bare figure, so the «20» of «de 10:00 a 20:00» exonerated an invented
    «20 €». Only an amount in the evidence backs an amount said."""
    ev = ["RESPUESTA DEL BUSCADOR: Abre de 10:00 a 20:00 horas. La entrada general cuesta 15 euros."]
    said = [{"who": "zaelar", "text": "La entrada cuesta 20 euros.", "at": 5}]
    assert verify.market_claims_before_delivery(said, {}, {}, [], ev)["n"] == 1
    said = [{"who": "zaelar", "text": "The ticket is €15.", "at": 5}]
    assert verify.market_claims_before_delivery(said, {}, {}, [], ev)["n"] == 0
