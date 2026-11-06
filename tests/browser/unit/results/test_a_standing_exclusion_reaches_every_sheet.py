"""A standing exclusion reaches every sheet (node 12.838, V2-838).

search-buy-used-car ES (2026-11-02). He said «evita coches de Flexicar, anótalo como regla personal». The rule was
stored as a sentence nobody applies, so the next car search showed Flexicar again. The class: a standing preference
is DATA with a scope. It is shaped ONCE, when written, into `{excluded: [names]}` at the `search` scope — by the
shaping model, never by a verb table — and the sheet's door reads the rules active on its path through the cascade,
every time, so a rule from an earlier session reaches a search that starts clean. A row it rules out names the rule.

The model's answer is injected (`shape._chat`): what is under test is what the engine DOES with a shaped row.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import rules
from nucleo.flash import style_directive
from rules import shape
from rules import store as rstore
from widgets.results import category_gate
from widgets.results import data as sheet

CARS = [
    {"title": "Mercedes-Benz GLC 220 d 4Matic AMG Line", "price": "€ 23.499",
     "url": "https://www.autoscout24.es/anuncios/mercedes-benz-glc-220-d-4matic-a7a15bb8"},
    {"title": "GLC 220d 4MATIC (2020)", "subtitle": "Negro · FLEXICAR COSLADA (Madrid)", "price": "23.990 €",
     "url": "https://www.autoscout24.es/anuncios/mercedes-benz-glc-220d-4matic-negro-5b68d80e"},
    {"title": "Mercedes-Benz GLC 220d 4MATIC 2019", "price": "24.900 €",
     "url": "https://www.flexicar.es/mercedes-benz/glc/7731"},
    {"title": "Mercedes-Benz GLC 300e 2021", "price": "29.900 €", "url": "https://www.coches.net/glc-300e-48211"},
]
FLATS = [
    {"title": "2-bed flat in Alfama, long term", "price": "€1,350", "url": "https://www.idealista.pt/en/imovel/3301"},
    {"title": "Bright 2BR in Graça", "price": "€1,420", "url": "https://www.airbnb.com/rooms/99812"},
    {"title": "Two-bedroom apartment, Arroios", "price": "€1,290", "url": "https://www.imovirtual.com/anuncio/88"},
]
RULE_ES = "evita coches de Flexicar, anótalo como regla personal"
RULE_EN = "never show me Airbnb"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    rules._reset_for_tests()
    yield
    rules._reset_for_tests()


class _Sess:
    directive = ""


def _say(monkeypatch, sentence, rows):
    monkeypatch.setattr(shape, "_chat", lambda system, user: json.dumps({"op": "add", "say": "ok", "rows": rows}))
    return asyncio.run(style_directive.write_rule(sentence, sentence, lambda *a, **k: None, _Sess(), speak=False))


def _excludes(names, scope="search"):
    return [{"scope": scope, "kind": "pref", "key": "excluded", "value": names}]


def _titles(rows):
    return [r["title"] for r in rows]


def test_a_rule_that_rules_something_out_is_stored_as_names_at_the_search_scope(monkeypatch):
    res = _say(monkeypatch, RULE_ES, _excludes(["Flexicar"]))
    (row,) = res["stored"]
    assert (row["scope"], row["key"], row["value"], row["text"]) == ("search", "excluded", ["Flexicar"], RULE_ES)
    _say(monkeypatch, RULE_EN, _excludes("Airbnb"))
    got = [(n, r["text"]) for n, r in rules.excluded(rules.path(surface=rules.SEARCH, widget="results"))]
    assert got == [("Flexicar", RULE_ES), ("Airbnb", RULE_EN)], "a second exclusion ADDS; it never replaces the first"


def test_the_door_rules_out_by_title_subtitle_or_link_and_names_the_rule(monkeypatch):
    _say(monkeypatch, RULE_ES, _excludes(["Flexicar"]))
    data = {"asked": "Quiero comprar un Mercedes GLC 220d de segunda mano", "items": []}
    on, extra = category_gate.gate(data, CARS, {})
    assert _titles(on) == [CARS[0]["title"], CARS[3]["title"]]
    assert {r["why"] for r in data["rejected"]} == {f"your rule: «{RULE_ES}»"}
    assert "your rule" in extra["note_for_worker"], "the worker is told why, in the rule's words"


def test_a_name_his_rule_rules_out_is_never_read_as_his_subject(monkeypatch):
    """His own words may name it («…pero nada de Flexicar»): the capital is not a subject every row must carry."""
    _say(monkeypatch, RULE_ES, _excludes(["Flexicar"]))
    data = {"asked": "Busco un GLC 220d, pero nada de Flexicar", "items": []}
    on, _ = category_gate.gate(data, CARS, {})
    assert _titles(on) == [CARS[0]["title"], CARS[3]["title"]]


def test_a_rule_from_an_earlier_session_reaches_a_new_search_that_starts_clean(monkeypatch):
    _say(monkeypatch, RULE_EN, _excludes(["Airbnb"]))
    rstore._conns.clear()                      # a new process: nothing in memory, only the table on disk
    rstore._invalidate()
    sid = "t2838new"
    res = sheet.apply_action("criteria", {"sheet": sid, "criteria": {"goal": "Two-bedroom flat to rent in Lisbon"}})
    assert res["ok"] and "excluded" not in sheet.view_data(sid)["criteria"], "the new sheet declares nothing"
    sheet.apply_action("present", {"sheet": sid, "items": list(FLATS)})
    view = sheet.view_data(sid)
    assert _titles(view["items"]) == [FLATS[0]["title"], FLATS[2]["title"]]
    assert [r["why"] for r in view["rejected"]] == [f"your rule: «{RULE_EN}»"]


def test_the_sheet_on_screen_meets_the_rule_the_moment_it_is_written(monkeypatch):
    sid = "t2838now"
    sheet.store.save(sheet.sheet_key(sid), {"title": "Mercedes GLC 220d", "asked": "Quiero un GLC 220d",
                                            "items": list(CARS), "pool": list(CARS)})
    _say(monkeypatch, RULE_ES, _excludes(["Flexicar"]))
    view = sheet.view_data(sid)
    assert _titles(view["items"]) == [CARS[0]["title"], CARS[3]["title"]]
    assert _titles(view.get("pool") or []) == [CARS[0]["title"], CARS[3]["title"]], "the gathered lot too"


def test_a_rule_he_switched_off_rules_nothing_out(monkeypatch):
    (row,) = _say(monkeypatch, RULE_ES, _excludes(["Flexicar"]))["stored"]
    rules.set_active(row["id"], False)
    on, _ = category_gate.gate({"asked": "Quiero un GLC 220d", "items": []}, CARS, {})
    assert _titles(on) == _titles(CARS)
