"""`search.find()` — one door, one shape, whichever module ran (V2-782 T1.3 / T5.1)."""
from __future__ import annotations

import pytest

import search
from search import hooks, web
from search.result import Candidate, candidate_from_row


@pytest.fixture
def fake_web(monkeypatch):
    calls: list = []

    def fake(q, k=5, mode="answer"):
        calls.append((q, k, mode))
        return {"query": q, "answer": "El Prado abre a las 10:00." if mode == "answer" else "", "source": "gemini",
                "ai": True, "results": [
                    {"title": "Museo del Prado — horarios", "snippet": "Abierto de 10 a 20 h", "url": "https://museodelprado.es/visita"},
                    {"title": "Los 10 mejores museos de Madrid", "snippet": "", "url": "https://blog.es/best/museos"},
                    {"title": "Alurin CoreVision 27 4K por 149,99 €", "snippet": "", "url": "https://shop/a"}]}

    monkeypatch.setattr(web, "search", fake)
    return calls


def test_a_fact_carries_the_answer_the_candidates_and_the_pages(fake_web):
    res = search.find("¿a qué hora abre el Prado?", verdicts={"escalate_or_inline": ("handle_inline", 0.9)})
    assert res.route == "inline_fact" and res.provider == "gemini" and res.ok()
    assert res.answer.startswith("El Prado")
    assert [c.title for c in res.candidates] == ["Museo del Prado — horarios", "Alurin CoreVision 27 4K por 149,99 €"]
    assert res.candidates[1].price == "149,99 €" and res.candidates[0].origin == "web"
    assert [p.title for p in res.pages] == ["Los 10 mejores museos de Madrid"]
    assert fake_web[0][2] == "answer"
    d = res.to_dict()
    assert d["ok"] and d["n"] == 2 and d["route"] == "inline_fact" and "took_ms" in d


def test_the_rows_are_the_sheets_closed_schema(fake_web):
    res = search.find("museos", route="inline_fact")
    rows = res.rows()
    assert rows and set(rows[0]) <= {"title", "subtitle", "price", "url", "image", "facts"}
    labels = {f["label"] for f in rows[0]["facts"]}
    assert labels & {"Origen", "Origin"}
    back = candidate_from_row(rows[0])
    assert back.origin == "web" and back.title == rows[0]["title"]
    srcs = res.source_rows()
    assert any(s["status"] == "page" for s in srcs)


def test_a_local_service_without_a_directory_asks_the_lead_chain(fake_web, monkeypatch):
    monkeypatch.delenv("FOURSQUARE_SERVICE_KEY", raising=False)
    res = search.find("un fontanero", route="local_service", k=3)
    assert fake_web[-1][2] == "results" and fake_web[-1][1] >= 10
    assert res.provider == "gemini" and res.needs == ""


def test_a_commission_the_service_cannot_run_comes_back_as_needs(fake_web):
    res = search.find("compárame tres seguros", route="brain_worker")
    assert (res.needs, res.candidates, res.criteria["n_final"]) == ("brain_worker", [], 3)
    assert not fake_web, "no network for a module the caller must commission"
    res2 = search.find("mira en Idealista", route="listing", named_site=True)
    assert res2.route == "browser" and res2.needs == "browser"


def test_a_collapsed_chain_is_a_failure_not_an_exception(monkeypatch):
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "", "results": [], "source": "none", "ai": False,
        "failure": {"kind": "captcha", "detail": "ddg: challenge"}})
    res = search.find("tiempo en Soria", route="inline_fact")
    assert not res.ok() and res.failure["kind"] == "captcha"
    assert res.sources[0].status == "error"


def test_a_provider_that_explodes_is_a_failure_too(monkeypatch):
    def boom(q, k=5, mode="answer"):
        raise ValueError("payload")
    monkeypatch.setattr(web, "search", boom)
    res = search.find("x", route="inline_fact")
    assert res.failure["kind"] == "error" and "ValueError" in res.failure["detail"]


def test_an_empty_request_is_refused_quietly():
    res = search.find("   ")
    assert res.failure["kind"] == "empty" and res.candidates == []


def test_the_service_tells_the_timeline_when_a_host_listens(fake_web, monkeypatch):
    seen = []
    monkeypatch.setattr(hooks, "emit", lambda fam, label, **kw: seen.append((fam, label, kw)))
    search.find("¿a qué hora abre el Prado?", route="inline_fact")
    assert seen and seen[0][0] == "search" and seen[0][2]["extra"]["route"] == "inline_fact"


def test_a_candidate_row_keeps_phone_rating_and_availability_as_facts():
    c = Candidate(title="Fontanería A", phone="600 1", rating="8.7/10", availability="open now", origin="local")
    row = c.to_row()
    values = {f["value"] for f in row["facts"]}
    assert {"600 1", "8.7/10", "open now"} <= values
    back = candidate_from_row(row)
    assert (back.phone, back.rating, back.availability, back.origin) == ("600 1", "8.7/10", "open now", "local")


def test_a_phone_a_business_wrote_in_its_title_is_its_datum(monkeypatch):
    """Measured on Z.ai leads 2026-10-10: the phone is in the title. By SHAPE, never «nine digits» (V2-321)."""
    from search import candidacy
    assert candidacy.lone_phone("Fontaneros Urgentes en Madrid - 622 65 44 32") == "622 65 44 32"
    assert candidacy.lone_phone("FONTANERO URGENTE MADRID 24 HORAS 630443211") == "630443211"
    assert candidacy.lone_phone("Mr. Rooter Plumbing (415) 906-2456") == "(415) 906-2456"
    assert candidacy.lone_phone("Five Star Plumbing +1 415-724-7083") == "+1 415-724-7083"
    assert candidacy.lone_phone("Publicado el 10/10/2026 a las 10:30") == ""
    assert candidacy.lone_phone("Pedido 2026101012345 recibido") == ""
    assert candidacy.lone_phone("Tel 622 65 44 32 y 910 27 72 81") == "", "two phones is a directory line, not one business"
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "", "source": "zai", "results": [
            {"title": "Fontaneros Urgentes en Madrid - 622 65 44 32", "snippet": "24/7", "url": "https://rubio.es"}]})
    res = search.find("fontanero urgente", route="local_service")
    assert res.candidates[0].phone == "622 65 44 32"
    labels = {f["label"]: f["value"] for f in res.rows()[0]["facts"]}
    assert "622 65 44 32" in labels.values()
