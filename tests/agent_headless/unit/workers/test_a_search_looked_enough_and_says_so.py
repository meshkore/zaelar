"""V2-840 — a search that looked enough, and says so.

Cloud car search (2026-11-02, Volvo XC60, «the five best»): ONE portal swept, 15 ads, «short market», and the errand's
end state was only `results.empty = false`; the brief had asked for dozens of candidates and nothing measured it.
Discovery pulled another country's classifieds. After delivery, «only the peninsula» wrote `criteria.excluded` on the
sheet and the finished errand never reopened: the row on an island stayed.

The class, and the fix this file holds to:
  · H1 — breadth is the COMPOSER's, per domain and market: no floor, no numeral reader; only a cost cap.
  · H2 — the brief's own target is part of the end state: short of it, ONE model question («enough?») decides one more
    bounded round of the same errand, or a delivery that says why; a model that fails delivers «not judged».
  · H3 — the brief names the market and its sources; discovery carries the market; the question asks for more sources.
  · H4 — the worker's brief says media goes in with priority after the information asked for.
  · H5 — a criteria change on a FINISHED errand's sheet updates its brief and reopens the SAME errand, every time.
Variants: used cars ES, flats to rent EN, and a scarce product (only five exist) whose shortfall is accepted.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import breadth
from nucleo.circuit import reopen
from nucleo.circuit import spec as _spec
from nucleo.circuit import verify as _verify
from nucleo.workers import brief as research
from nucleo.workers.session import SessionRecord

CARS = {"request": "busca un Volvo XC60 diésel de 2020 o más, menos de 120.000 km, las cinco mejores ofertas",
        "goal": "Las mejores ofertas de Volvo XC60 diésel 2020+ en España", "domain": "coches de segunda mano",
        "hard": ["Volvo XC60", "diésel", "2020 o posterior"], "breadth": {"min_candidates": 60},
        "market": {"country": "España", "category": "coches de segunda mano"},
        "sources": ["coches.net", "milanuncios", "AutoScout24"], "deliverable": {"n_final": 5}}
FLATS = {"request": "find me a two-bedroom flat to rent in Manchester under £1,200",
         "goal": "Two-bedroom flats to rent in Manchester under £1,200", "domain": "residential rentals",
         "hard": ["2 bedrooms", "≤ £1,200 pcm"], "breadth": {"min_candidates": 30},
         "market": {"country": "United Kingdom", "category": "flats to rent"},
         "sources": ["Rightmove", "Zoopla", "OpenRent"], "deliverable": {"n_final": 10}}
SCARCE = {"request": "find me a Fazioli F308 concert grand for sale in Europe",
          "goal": "A Fazioli F308 for sale in Europe", "domain": "concert grand pianos",
          "hard": ["Fazioli F308"], "breadth": {"min_candidates": 20}, "deliverable": {"n_final": 5}}


def _brief(spec: dict) -> dict:
    raw = json.dumps({"research": True, **{k: v for k, v in spec.items() if k != "request"}}, ensure_ascii=False)
    b = research.parse(raw, request=spec["request"])
    b["request"] = spec["request"]
    return b


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    _spec.reset()
    reopen._PENDING.clear()
    sent: list = []
    from nucleo.acts import errand as escalate

    def _esc(req, context=None):
        sent.append((req, context or {}))
        return 900 + len(sent)
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", _esc)
    monkeypatch.setattr(_verify, "check", lambda dw, now=None: True if dw else None)
    asked: list = []
    yield sent, asked
    _spec.reset()
    reopen._PENDING.clear()
    memdb.reset_db()


def _sheet(sheet: str, *, rows: int, explored: int, sources: list[dict]) -> None:
    from widgets.results import data as _d
    data = _d._empty()
    data["items"] = [{"title": f"Candidate {i}", "url": f"https://example.test/{sheet}/{i}"} for i in range(rows)]
    data["summary"] = {"explored": explored, "state": "delivering"}
    data["sources"] = sources
    _d._save(data, sheet)


def _record(spec: dict, sheet: str, tid: str = "7") -> SessionRecord:
    research.save(tid, _brief(spec))
    rec = SessionRecord(task_id=tid, goal=spec["goal"], kind="research", uid=sheet, sheet=sheet, status="done", ok=True)
    rec.done_when = {"all": [{"widget": "results", "field": "empty", "is": "false"}]}
    rec.result_summary = "Here are the results."
    return rec


def _model(monkeypatch, asked: list, answer):
    async def _ask(msgs, timeout):
        asked.append(msgs)
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer, ensure_ascii=False)
    monkeypatch.setattr(breadth, "_ask", _ask)


# ── H1 · breadth is the composer's ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("spec,minc,nfin", [(CARS, 60, 5), (FLATS, 30, 10), (SCARCE, 20, 5)])
def test_the_brief_target_is_what_the_composer_reasoned(spec, minc, nfin):
    b = _brief(spec)
    assert b["breadth"]["min_candidates"] == minc and b["deliverable"]["n_final"] == nfin


def test_a_small_number_is_kept_and_only_cost_caps_a_large_one():
    small = research.parse(json.dumps({"research": True, "goal": "x", "breadth": {"min_candidates": 4}}),
                           request="give me the twenty best")
    assert small["breadth"]["min_candidates"] == 4, "no floor of ours, and no numeral reader over his words"
    big = research.parse(json.dumps({"research": True, "goal": "x", "breadth": {"min_candidates": 10 ** 6}}))
    assert big["breadth"]["min_candidates"] == research._MIN_CANDIDATES_CAP


def test_no_floor_and_no_default_count_exist():
    from nucleo.workers import brief_parse
    for gone in ("_MIN_CANDIDATES_FLOOR", "_N_FINAL_DEFAULT", "_said_breadth"):
        assert not hasattr(brief_parse, gone) and not hasattr(research, gone), gone
    shown = research.parse(json.dumps({"research": True, "goal": "x"}))
    assert shown["deliverable"]["n_final"] == 0 and shown["breadth"]["min_candidates"] == 0


def test_the_composer_is_asked_to_reason_the_number_for_its_market():
    s = research._SYSTEM
    assert "defendible en ESTE dominio y ESTE mercado" in s and "mercado pequeño" in s
    assert '"min_candidates": 40' not in s and '"n_final": 10' not in s, "an example number is a number of ours"
    assert "pon 10" not in s and "decide tú cuántas merecen presentarse" in s


# ── H3 · the market and its sources ──────────────────────────────────────────────────────────────────────────
def test_the_brief_carries_market_and_sources_to_the_worker():
    b = _brief(CARS)
    assert b["market"] == {"country": "España", "category": "coches de segunda mano"}
    assert b["sources"] == ["coches.net", "milanuncios", "AutoScout24"]
    block = research.to_prompt_block(b)
    assert "España · coches de segunda mano" in block and "coches.net" in block and "milanuncios" in block
    assert '"market"' in research._SYSTEM and '"sources"' in research._SYSTEM


@pytest.mark.parametrize("market", ["España coches de segunda mano", "United Kingdom flats to rent"])
def test_discovery_carries_the_market(monkeypatch, market):
    from search import listing as L
    from search import web as websearch
    seen = []
    monkeypatch.setattr(websearch, "search", lambda q, k=10, mode="answer": seen.append(q) or {"results": []})
    L._free_discover(L.ListingQuery(text="volvo xc60 diesel", condition="used", market=market))
    assert seen and market in seen[0] and seen[0].startswith("volvo xc60 diesel used")


def test_a_workers_search_carries_its_briefs_market(world, monkeypatch):
    import search
    from nucleo.workers import web_search_bridge as bridge
    from nucleo.workers import search_budget
    got = {}
    monkeypatch.setattr(search_budget, "spend", lambda _tid: "")
    monkeypatch.setattr(search, "find", lambda q, **kw: got.update(kw) or (_ for _ in ()).throw(RuntimeError("stop")))
    rec = _record(FLATS, "s-flats")
    asyncio.run(bridge.run({"args": {"query": "2 bed flat Manchester"}}, rec))
    assert got.get("market") == "United Kingdom flats to rent"


# ── H4 · media first, after the information ─────────────────────────────────────────────────────────────────
def test_the_worker_is_told_media_goes_in_with_priority():
    block = research.to_prompt_block(_brief(FLATS))
    assert "MATERIAL VISUAL CON PRIORIDAD" in block and "después de la información pedida" in block


# ── H2 · the harness asks whether it was enough ───────────────────────────────────────────────────────────────
def test_a_short_sweep_judged_not_enough_runs_another_round_of_the_same_errand(world, monkeypatch):
    sent, asked = world
    _sheet("s-cars", rows=3, explored=15, sources=[{"name": "AutoScout24 España", "status": "ok", "found": 15}])
    rec = _record(CARS, "s-cars")
    _model(monkeypatch, asked, {"enough": False, "why": "Solo se barrió un portal.",
                                "next": "barrer coches.net y milanuncios", "more_sources": ["coches.net"]})
    asyncio.run(breadth.judge(rec))
    verdict = circuit.close(rec, relay_cap=3)
    assert verdict == "started" and len(sent) == 1
    req, ctx = sent[0]
    assert "[ARNÉS]" in req and "coches.net" in req and "AutoScout24 España" in req and "15" in req
    assert ctx["task_uid"] == "s-cars" and ctx["sheet"] == "s-cars" and ctx["resume"] == {"brief_task": "s-cars"}
    # the ONE question carried the brief, the progress and the sources used, and asked about more sources
    q = json.loads(asked[0][1]["content"])
    assert q["target"]["min_candidates"] == 60 and q["progress"]["explored"] == 15
    assert q["progress"]["sources"][0]["name"] == "AutoScout24 España" and "MORE SOURCES" in asked[0][0]["content"]
    assert research.load("s-cars"), "the brief is kept under the commission's durable id for the continuation"


def test_a_scarce_market_is_delivered_with_its_reason(world, monkeypatch):
    sent, asked = world
    _sheet("s-piano", rows=3, explored=5, sources=[{"name": "Fazioli dealers", "status": "ok", "found": 5}])
    rec = _record(SCARCE, "s-piano")
    _model(monkeypatch, asked, {"enough": True, "why": "Only five F308s are for sale in Europe right now.",
                                "next": "", "more_sources": []})
    asyncio.run(breadth.judge(rec))
    assert circuit.close(rec, relay_cap=3) == "met" and not sent
    from widgets.results import data as _d
    assert _d.view_data("s-piano")["summary"]["note"].startswith("Only five F308s")


def test_a_judge_that_fails_delivers_and_says_not_judged(world, monkeypatch):
    sent, asked = world
    _sheet("s-flats", rows=4, explored=9, sources=[{"name": "Rightmove", "status": "blocked"}])
    rec = _record(FLATS, "s-flats")
    _model(monkeypatch, asked, TimeoutError("no answer"))
    out = asyncio.run(breadth.judge(rec))
    assert out["judged"] is False and circuit.close(rec, relay_cap=3) == "met" and not sent
    from widgets.results import data as _d
    assert _d.view_data("s-flats")["summary"]["note"] == _d.note_text("breadth_not_judged", "")


def test_a_search_that_met_its_target_asks_nothing(world, monkeypatch):
    sent, asked = world
    _sheet("s-cars", rows=5, explored=64, sources=[{"name": "coches.net", "status": "ok", "found": 40}])
    rec = _record(CARS, "s-cars")
    _model(monkeypatch, asked, {"enough": False})
    asyncio.run(breadth.judge(rec))
    assert not asked and circuit.close(rec, relay_cap=3) == "met" and not sent


def test_the_extra_round_is_bounded_and_then_delivers_saying_why(world, monkeypatch):
    sent, asked = world
    _sheet("s-cars", rows=3, explored=15, sources=[{"name": "AutoScout24 España", "status": "ok"}])
    rec = _record(CARS, "s-cars")
    rec.relay_gen = 3                                     # the relaunch budget is spent
    _model(monkeypatch, asked, {"enough": False, "why": "Faltan portales.", "next": "coches.net"})
    asyncio.run(breadth.judge(rec))
    assert circuit.close(rec, relay_cap=3) == "met" and not sent
    from widgets.results import data as _d
    assert _d.view_data("s-cars")["summary"]["note"] == "Faltan portales."


# ── H5 · a correction reopens the finished errand ────────────────────────────────────────────────────────────
def _finished(uid: str, spec: dict, state: str = "done") -> None:
    ts.task_put({"id": uid, "goal": spec["goal"], "title": spec["goal"], "kind": "research", "state": state,
                 "sheet": uid, "surface": "lista", "created_at": int(time.time())})
    research.save(uid, _brief(spec))
    _sheet(uid, rows=3, explored=15, sources=[{"name": "AutoScout24 España", "status": "ok"}])


def _criteria(uid: str, **upd) -> dict:
    from widgets.results import data as _d
    return _d.apply_action("criteria", {"sheet": uid, **upd})


def test_a_correction_on_a_finished_search_reopens_the_same_errand_every_time(world):
    sent, _asked = world
    _finished("u-cars", CARS)
    out = _criteria("u-cars", changes=["coches siempre en la península"], excluded=["islas", "Ceuta", "Melilla"])
    assert out["ok"] and out.get("reopened") and len(sent) == 1
    req, ctx = sent[0]
    assert ctx["task_uid"] == "u-cars" and ctx["sheet"] == "u-cars" and ctx["resume"] == {"brief_task": "u-cars"}
    assert "península" in req and "sus propios datos" in req, "the worker judges each row by its facts"
    b = research.load("u-cars")
    assert "islas" in b["excluded"] and "coches siempre en la península" in b["feedback"]
    assert "islas" in research.to_prompt_block(b)
    # the same change again is already in its brief: met, nothing relaunched
    reopen._PENDING.clear()
    assert not _criteria("u-cars", changes=["coches siempre en la península"]).get("reopened") and len(sent) == 1
    # …and the next correction reopens it again
    assert _criteria("u-cars", changes=["que no sea blanco"]).get("reopened") and len(sent) == 2


def test_a_correction_on_a_finished_flat_search_reopens_it_en(world):
    sent, _asked = world
    _finished("u-flats", FLATS)
    assert _criteria("u-flats", hard=["not on the ground floor"]).get("reopened")
    assert sent[0][1]["task_uid"] == "u-flats" and "not on the ground floor" in research.load("u-flats")["hard"]


def test_a_correction_while_the_errand_runs_is_not_a_reopen(world):
    sent, _asked = world
    _finished("u-live", FLATS, state="running")
    assert not _criteria("u-live", hard=["balcony"]).get("reopened") and not sent
