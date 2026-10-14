"""Node 2.687 — a claim a source carries stands: the false-positive golden of the row-claims guard.

A false cut removes a REAL delivery, so the guard is measured against what was right: every row of every recorded
sheet (`tests/search/fixtures/sheets`, the 2026-10-14 sheets) quoted as the delivery backstop quotes it and named
before its price must stand; and the correct replies of the 2026-10-14 rounds stand verbatim — the sofa's «only six
months used» (the listing's own title, kept whole by node 2.685), the TV rows the judge filed «in no source» (on the
sheet at that turn), the washer's first answer over the in-turn listing, and attributes a row's facts say «yes» to.

Disarm: `claim_vocab.carries` returning False → the sofa and the verified-facts tests go red.
"""
from __future__ import annotations

import json

import pytest

from nucleo.flash import claim_backing as B
from nucleo.flash import row_claims as R

from ._claim_scene import RECORDED, SHEETS, SOFA, SOFA_HEARD, TV, TV_924, review, said

_ALL = sorted(RECORDED.glob("*.json")) + sorted(SHEETS.glob("*.json"))


@pytest.mark.parametrize("path", _ALL, ids=lambda p: p.stem)
def test_every_recorded_row_quoted_or_priced_stands(path, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    rows = B.rows_of(json.loads(path.read_text(encoding="utf-8")))
    cut = []
    for r in rows:
        it = r["item"]
        if r["rejected"] or not it.get("price"):
            continue
        for reply in (f"Actually, there are already candidates on the results sheet: «{it['title']} — {it['price']}».",
                      f"Best so far: {it['title']} at {it['price']}."):
            res = R.review(reply, None, "any news?", rows=rows, evidence=[], goals="", errand=True)
            cut += [c["sentence"] for c in res["cut"]]
    assert not cut, cut[:3]


def test_the_sofa_six_months_used_stands_on_the_listing_title(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert said(SOFA, SOFA_HEARD, sheets=("sofa_us",)) == SOFA


def test_the_rows_the_judge_called_unbacked_were_on_the_sheet(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert said(TV, "any news?", sheets=("tv_us",)) == TV
    assert said(TV_924, "ok cool", sheets=("tv_us",)) == TV_924


def test_attributes_a_row_says_yes_to_stand(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    reply = "The Fnac one at 929.88 is new and sealed, and it's the standard iPhone 17 with 256 GB."
    assert said(reply, "is the Fnac one new?", sheets=("phone_final_us",)) == reply
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    verified = {"title": "Evvo TERRA N", "price": "299,90 €", "facts": [
        {"label": "Capacidad de carga exactamente 8 kg", "value": "sí — título de la ficha: «Capacidad 8 Kg, 1400 RPM»"},
        {"label": "Clase energetica declarada A (no A+, ni lavado/centrifugado)", "value": "sí — «E. Energética A»"}]}
    rows = B.rows_of({"items": [verified], "criteria": {"hard": [f["label"] for f in verified["facts"]]}})
    es = "Sí, la Evvo TERRA N de 299,90 es de 8 kilos y clase A."
    assert R.review(es, None, "¿es de 8 kilos y clase A?", rows=rows, evidence=[], goals="", errand=True)["parts"] == [es]


def test_the_washer_first_answer_over_the_in_turn_listing_stands(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    items = [{"title": "Lavadora carga frontal - NILSON…", "full_title": "Lavadora carga frontal - NILSON NL8200AI, 8 kg, "
              "11 programas, Blanco", "price": "264.90 EUR"},
             {"title": "Lavadora carga frontal - Bosch…", "full_title": "Lavadora carga frontal - Bosch WGE03200ES, 8 kg, "
              "1400 rpm, Blanco", "price": "379 EUR"},
             {"title": "Haier I-Pro Series 1 HW80-BP14929A", "price": "339 EUR"}]
    reply = ("He encontrado 8 lavadoras, todas por debajo de 400 euros. La más barata es la Nilson NL8200AI por 264,90, y "
             "como opción más equilibrada tienes la Bosch WGE03200ES por 379 o la Haier I-Pro por 339.")
    rows = B.rows_of({"items": items})
    window = [{"role": "user", "content": "Búscame una lavadora de 8 kilos, clase A, por menos de 400 euros."}]
    assert R.review(reply, window, "", rows=rows, evidence=[], goals="", errand=True)["parts"] == R._sentences(reply)
