"""The listing fast pass either SERVES the turn or hands off honestly — never both, never neither (V2-556 P1).

What is nailed down here, each half born measurable in the 2026-09-02 baseline round:
  · enough listings → they are PRESENTED on a sheet with their sources and NO worker is launched
    (`search-buy-used-car` round 22 failed exactly the delivery half: rows existed, nobody spoke them);
  · not enough → the SAME sheet keeps the partial findings and the escalation carries it in its context,
    so the Brain Worker inherits the box the operator is already watching (the V2-117 relay seam);
  · the module never raises into the turn, whatever the search does.
"""
from __future__ import annotations

import pytest

from nucleo.flash import listing_turn


@pytest.fixture()
def rig(monkeypatch):
    """A recording rig around everything listing_turn touches: search result is programmable, sheet writes and
    escalations are recorded, nothing reaches disk or the bus."""
    calls = {"present": [], "begin": [], "escalate": [], "emit": []}

    import nucleo.listing_search as LS
    import widgets.results.data as sheet
    import nucleo.flash.escalate as esc
    import voice.observer as obs

    def fake_search(q):
        return rig_state["result"]

    rig_state = {"result": {"items": [], "sources": [], "needs_browser": True, "reason": "empty"}}
    monkeypatch.setattr(LS, "search", fake_search)
    monkeypatch.setattr(sheet, "begin_task", lambda title="", fresh=True, sheet="": calls["begin"].append(
        {"title": title, "fresh": fresh, "sheet": sheet}) or {"ok": True})
    calls["rename"] = []
    monkeypatch.setattr(sheet, "rename_task", lambda title="", sheet="": calls["rename"].append(
        {"title": title, "sheet": sheet}) or {"ok": True})
    # V2-570 — the delivery record is in-RAM state shared with dispatch's continuity gate: isolate it.
    from nucleo.workers import ended as _ended
    _ended._LISTING_DELIVERIES.clear()
    monkeypatch.setattr(sheet, "apply_action", lambda action, payload=None: calls["present"].append(
        {"action": action, "payload": payload or {}}) or {"ok": True, "shown": len((payload or {}).get("items", []))})
    monkeypatch.setattr(sheet, "prune_sheets", lambda *a, **k: 0)
    monkeypatch.setattr(sheet, "instance_id", lambda s="": f"results::{s}" if s else "results")
    monkeypatch.setattr(esc, "escalate_to_slowbrain",
                        lambda request, context=None: calls["escalate"].append(
                            {"request": request, "context": dict(context or {})}) or 71)
    monkeypatch.setattr(obs, "emit", lambda *a, **k: calls["emit"].append({"a": a, "k": k}))
    return rig_state, calls


def _items(n, price=1200.0):
    return [{"title": f"Anuncio {i}", "url": f"https://mkt.example/{i}", "price": price + i,
             "currency": "EUR", "source": "mkt.example", "location": "Madrid",
             "attributes": {"mileage": f"{40 + i}k km"}} for i in range(n)]


def test_enough_listings_are_presented_and_no_worker_is_launched(rig):
    state, calls = rig
    state["result"] = {"items": _items(6), "sources": [{"tier": "fetch", "target": "mkt.example",
                                                        "status": "ok", "n": 6, "kept": 6}],
                      "needs_browser": False, "reason": ""}
    out = listing_turn.run("coche diésel segunda mano", price_max=12000,
                           operator_text="Búscame un coche de segunda mano diésel por menos de 12 mil")
    assert out["delivered"] is True and out["n"] == 6
    assert calls["escalate"] == []                      # served in-turn: no worker, no racing errand
    assert calls["present"], "the rows never reached the sheet — the exact defect of round 22"
    payload = calls["present"][0]["payload"]
    assert len(payload["items"]) == 6
    assert payload["items"][0]["price"].endswith("EUR") or "€" in payload["items"][0]["price"] or \
        payload["items"][0]["price"], "the printed price lost its currency"
    assert payload["sources"], "sources are the difference between a result and a rumour"
    assert payload["sheet"] == out["sheet"] and out["sheet"], "delivery must name the sheet it went to"


def test_not_enough_escalates_with_the_same_sheet_inherited(rig):
    state, calls = rig
    state["result"] = {"items": _items(2), "sources": [{"tier": "fetch", "target": "wall.example",
                                                        "status": "blocked", "note": "403"}],
                      "needs_browser": True, "reason": "only 2 found"}
    out = listing_turn.run("moto 125", operator_text="Búscame una moto de 125 por menos de 2500")
    assert out["delivered"] is False and out["escalated"] == 71
    assert len(calls["escalate"]) == 1
    esc = calls["escalate"][0]
    assert esc["request"] == "Búscame una moto de 125 por menos de 2500", \
        "the worker gets the OPERATOR's words, not the model's reformulation (V2-135)"
    assert esc["context"].get("sheet") == out["sheet"] and out["sheet"], \
        "without the sheet in the context the worker opens a SECOND box (the V2-117 two-boxes defect)"
    assert esc["context"].get("surface") == "lista"
    # the partial findings were still delivered — the operator watches 2 rows, not a blank card
    assert calls["present"] and len(calls["present"][0]["payload"]["items"]) == 2


def test_a_search_that_explodes_never_reaches_the_turn(rig, monkeypatch):
    state, calls = rig
    import nucleo.listing_search as LS
    monkeypatch.setattr(LS, "search", lambda q: (_ for _ in ()).throw(RuntimeError("boom")))
    out = listing_turn.run("portátil", operator_text="quiero un portátil")
    assert out["delivered"] is False
    assert calls["escalate"], "a broken fast pass still hands the errand to the deep pass"


def test_compose_context_speaks_rows_without_urls():
    ctx = listing_turn.compose_context({"items": _items(3)})
    assert "Anuncio 0" in ctx and "Madrid" in ctx
    assert "https://" not in ctx, "the spoken context must never carry URLs — the voice would read them"


def test_empty_query_is_refused_without_side_effects(rig):
    state, calls = rig
    out = listing_turn.run("", operator_text="")
    assert out["delivered"] is False and out["n"] == 0
    assert calls["present"] == [] and calls["escalate"] == []


# ── V2-570 — the linear doctrine's half that lives HERE: the inherited box, and the delivery as a fact ────

def test_a_delivery_is_recorded_as_a_fact_the_engine_can_see(rig):
    """Measured on session 9dcff6f5: a delivered fast pass left NO trace a later escalation could match
    (`dedup_miss: live 0`), so the same hunt got a second sheet and a parallel worker."""
    from nucleo.workers import ended
    state, calls = rig
    state["result"] = {"items": _items(6), "sources": [], "needs_browser": False, "reason": ""}
    out = listing_turn.run("alquiler de catamaranes empresas",
                           operator_text="Búscame si hay empresas de alquiler de catamaranes en plan")
    rows = ended.recent_listing_deliveries()
    assert len(rows) == 1
    assert rows[0]["sheet"] == out["sheet"] and rows[0]["n"] == 6
    assert rows[0]["goal"] == "Búscame si hay empresas de alquiler de catamaranes en plan", \
        "the record keys on the OPERATOR's words — that is what the follow-up escalation will contain"


def test_a_hand_off_records_no_delivery(rig):
    """An insufficient pass escalates and a live session exists: the dedup already covers that side, and a
    delivery record here would arm the linear gate against a hunt that is actively being worked."""
    from nucleo.workers import ended
    state, calls = rig
    state["result"] = {"items": [], "sources": [], "needs_browser": True, "reason": "empty"}
    listing_turn.run("moto 125", operator_text="Búscame una moto de 125")
    assert ended.recent_listing_deliveries() == []


def test_an_inherited_sheet_is_reused_never_reminted(rig):
    state, calls = rig
    state["result"] = {"items": _items(5), "sources": [], "needs_browser": False, "reason": ""}
    out = listing_turn.run("catamaranes 45 pies Barcelona", operator_text="la caza afinada",
                           sheet="results--heredada")
    assert out["sheet"] == "results--heredada"
    assert calls["begin"] and calls["begin"][0]["sheet"] == "results--heredada"
    assert calls["present"][0]["payload"]["sheet"] == "results--heredada"


def test_an_inherited_sheet_with_nothing_found_is_not_wiped(rig):
    """`present` with an empty list REPLACES the items — on an inherited box that would erase the delivery
    the operator is reading, in exchange for nothing (the «estrenar = borrar» failure V2-259 closed)."""
    state, calls = rig
    state["result"] = {"items": [], "sources": [], "needs_browser": True, "reason": "empty"}
    out = listing_turn.run("catamaranes 45 pies", operator_text="la caza afinada", sheet="results--heredada")
    assert calls["begin"] == [] and calls["present"] == [], "the previous delivery must stay on screen"
    assert calls["rename"] and calls["rename"][0]["sheet"] == "results--heredada"
    assert calls["escalate"] and calls["escalate"][0]["context"].get("sheet") == "results--heredada", \
        "the deep pass continues in the SAME box"
    assert out["delivered"] is False
