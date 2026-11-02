"""The brain's three seams into the service (V2-782 F4 / T4.4): the brief asks the routing question, the shadow route
is emitted, a network agent's rows keep their rating, and the research brief keeps the size its composer read."""
from __future__ import annotations

from nucleo.cli import mesh as mesh_cli
from nucleo.acts import search as search_routing
from nucleo.turn import brief as turn_brief
from nucleo.workers import brief as research
from search.route import SEARCH_KEY


def test_the_brief_asks_which_search_module():
    qs = turn_brief.build("busca un fontanero", open_ids=[], running_goals=[])
    assert SEARCH_KEY in qs and set(qs[SEARCH_KEY]["criteria"]) == {
        "inline_fact", "listing", "local_service", "images", "browser", "brain_worker"}


def test_the_shadow_route_is_emitted_and_never_raises():
    seen = []
    rt = search_routing.shadow("¿a qué hora abre el Prado?", proposal="web_search", brief=None,
                               emit=lambda kind, label, **kw: seen.append((kind, label, kw)), channel="probe")
    assert rt is not None and rt.module == "inline_fact"
    assert seen[0][1].startswith("🧭") and seen[0][2]["extra"]["module"] == "inline_fact"
    assert search_routing.shadow("x", proposal="web_search", brief=None, emit=None, channel="voice") is None


def test_verdicts_are_read_from_the_brief(monkeypatch):
    answers = {SEARCH_KEY: {"choice": "listing", "confidence": 0.9},
               "escalate_or_inline": {"choice": "escalate", "confidence": 0.7}}
    monkeypatch.setattr(turn_brief, "read", lambda brief, key, fb, min_confidence=None:
                        ((answers[key]["choice"], answers[key]) if key in answers else (fb, None)))
    v = search_routing.verdicts_from_brief({"fake": True})
    assert v[SEARCH_KEY] == ("listing", 0.9) and v["escalate_or_inline"] == ("escalate", 0.7)
    assert search_routing.route_for("un piso", proposal="web_search", brief={"fake": True}).module == "listing"


def test_a_network_agents_rows_keep_rating_phone_and_say_where_they_came_from():
    rows = mesh_cli._rows_in({"hotels": [
        {"name": "Humphreys Half Moon Inn", "price": "$785", "url": "https://h/1", "rating": 8.8, "phone": "+1 619"},
        {"title": "Inyectores De Coche", "amount": "260", "link": "https://e/2"}]})
    assert rows[0]["title"] == "Humphreys Half Moon Inn" and rows[0]["price"] == "$785"
    values = {f["value"] for f in rows[0]["facts"]}
    assert "8.8" in values and "+1 619" in values
    assert any(v in values for v in ("agente de la red", "network agent"))
    assert mesh_cli._MESH_ROWS_CAP <= 8


def test_the_brief_takes_the_size_from_the_composer_who_read_his_words():
    """V2-840 H1: «a couple of recipes» is read by the composer (its prompt: «si DIJO un número, pon ESE»); the
    brief keeps what it declared, and his words are not re-read by a numeral table."""
    raw = ('{"research": true, "goal": "recetas sin gluten", "hard": ["sin gluten"], "breadth": {"min_candidates": 6},'
           ' "deliverable": {"n_final": 2}}')
    b = research.parse(raw, request="pull a couple of gluten-free recipes")
    assert b["deliverable"]["n_final"] == 2 and b["breadth"]["min_candidates"] == 6
    assert "pon ESE" in research._SYSTEM