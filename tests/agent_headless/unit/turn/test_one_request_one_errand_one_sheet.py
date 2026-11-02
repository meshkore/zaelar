"""One request, one errand, one sheet (V2-843, 2026-11-02).

A car request dictated in fragments: the first fragment parked on his «yes» (it moves money); each later fragment
reached the listing fast pass with the joined request. The flow door DID match the parked errand every time — and
answered «no flow», because a parked errand has no sheet yet. Each fragment minted a box of its own, its escalation
was absorbed into the parked errand, and three cards stayed on «Searching in depth…» with nobody behind them.

The decision was right; its consequence was not. A request a live errand covers lands in that errand's sheet — the
one its id names when it has none yet — and a folded launch never leaves its box behind.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo import sheets
from nucleo.acts import search_listing, search_sheet
from nucleo.dispatch import confirm
from nucleo.turn import flow_of, launches

REQ = {"query": "SUV"}

#: The same request in fragments, each turn carrying the joined text (EN as measured, ES, and a flat).
CAR_EN = ("I wanna buy a car. A new car.",
          ["let's focus on the car. I wanna... One of those big runners.",
           "let's focus on the car. I wanna... One of those big runners. Two or three good offers right now.",
           "let's focus on the car. I wanna... One of those big runners. Two or three good offers right now. "
           "The price, thirty, forty, fifty. Show it as soon as possible."])
CAR_ES = ("Quiero comprarme un coche nuevo.",
          ["Vale, el coche. Uno de esos todoterreno grandes.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas. Entre treinta y cincuenta mil.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas. Entre treinta y cincuenta mil. "
           "Enséñamelo cuanto antes."])
FLAT_EN = ("Find me a flat to rent in Madrid.",
           ["The flat, two bedrooms.", "The flat, two bedrooms. Near Retiro, under fifteen hundred."])


@pytest.fixture
def scene(monkeypatch):
    """No live flow but what each test parks; `fast_pass` replaced by a recorder; the judge answers by request."""
    launches.reset()
    calls: list[dict] = []
    judge = {"id": ""}

    def fake_pass(query, **kw):
        calls.append(kw)
        return {"delivered": False, "n": 0, "sheet": kw.get("sheet") or kw.get("new_sheet"), "escalated": 0,
                "reason": "", "ctx": ""}

    monkeypatch.setattr(search_listing, "fast_pass", fake_pass)
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", lambda text, live: judge["id"])
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [])
    monkeypatch.setattr("nucleo.acts.errand.pending", lambda: [])
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    yield calls, judge
    launches.reset()


def _park(tid: str, request: str, sheet: str = "") -> dict:
    confirm._PENDING_CONFIRM[tid] = {"request": request, "question": "¿Lo hago?", "sheet": sheet, "ts": time.time(),
                                     "context": {}}
    return confirm._PENDING_CONFIRM[tid]


@pytest.mark.parametrize("first, fragments", [CAR_EN, CAR_ES, FLAT_EN], ids=["car-en", "car-es", "flat-en"])
def test_every_fragment_of_a_parked_request_lands_in_its_errands_one_sheet(scene, first, fragments):
    calls, judge = scene
    parked = _park("2", first)
    judge["id"] = "2"            # the house judge's verdict (lexical containment or the model): this IS errand 2
    for text in fragments:
        asyncio.run(search_listing.listings({"text": text}, REQ))
    want = sheets.sheet_id_for("2")
    assert [c["sheet"] for c in calls] == [want] * len(fragments), \
        "a fragment of the parked request opened a box of its own instead of its errand's"
    assert not any(c["new_sheet"] for c in calls), "a covered request minted a sheet"
    assert parked["sheet"] == want, "the parked errand did not keep the sheet: his «yes» would open another"


def test_the_measured_fragment_is_covered_by_containment_alone(scene):
    """S4 measured: the joined fragment contains the parked request's words — the house yardstick hits without
    the model, so the consequence above is what was missing, not a matcher."""
    calls, _judge = scene
    _park("2", CAR_EN[0])
    flow = asyncio.run(flow_of.flow_of("let's let's focus on the car. I wanna buy a car. A new car. One of those "
                                       "big runners."))
    assert flow and flow["id"] == "2"


def test_an_escalation_in_flight_lends_its_errands_sheet(scene, monkeypatch):
    calls, judge = scene
    monkeypatch.setattr("nucleo.acts.errand.pending", lambda: [{"id": 9, "request": CAR_EN[0], "secs": 1}])
    judge["id"] = "esc:9"
    asyncio.run(search_listing.listings({"text": CAR_EN[1][0]}, REQ))
    assert calls[0]["sheet"] == sheets.sheet_id_for("9") and not calls[0]["new_sheet"]


def test_two_different_requests_are_two_errands_and_two_sheets(scene):
    calls, judge = scene
    _park("2", CAR_EN[0])
    judge["id"] = ""             # the judge says: not about the car
    asyncio.run(search_listing.listings({"text": "find me a used acoustic guitar in Barcelona"}, REQ))
    assert calls[0]["new_sheet"] and not calls[0]["sheet"], "a different request was folded into the car"
    assert confirm._PENDING_CONFIRM["2"]["sheet"] == "", "the car errand took a sheet it did not get"


# ── S3 · a launch folded into a parked errand never leaves its box behind ────────────────────────────────────

def _fold(monkeypatch, parked_sheet: str, own: str) -> list:
    from nucleo.dispatch import listener
    from voice import observer
    seen: list = []
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(listener, "_close_folded", lambda key: None)
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    _park("2", CAR_EN[0], parked_sheet)
    listener._absorb_into("2", CAR_EN[1][0], "3", {"sheet": own})
    return seen


def test_a_parked_errand_with_no_sheet_adopts_the_folded_launchs(monkeypatch):
    seen = _fold(monkeypatch, "", "ls1")
    assert confirm._PENDING_CONFIRM["2"]["sheet"] == "ls1", "the folded launch's box belongs to nobody"
    assert not any(a[:2] == ("widget", "close") for a, _ in seen)


def test_a_parked_errand_with_its_own_sheet_closes_the_duplicate(monkeypatch):
    seen = _fold(monkeypatch, "S2", "ls1")
    assert confirm._PENDING_CONFIRM["2"]["sheet"] == "S2"
    assert any(a[:2] == ("widget", "close") and kw["extra"]["id"] == "results::ls1" for a, kw in seen), \
        "the folded launch's sheet stayed on «Searching in depth…» with nobody behind it"


# ── S2 · a sheet its errand only NAMES is opened by the pass, never «inherited» empty ────────────────────────

def test_a_sheet_named_by_its_errand_opens_fresh_and_an_existing_one_is_inherited(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    seen: list = []
    monkeypatch.setattr("search.listing.search", lambda q: {"items": [], "sources": [], "needs_browser": True})
    monkeypatch.setattr(search_sheet, "_write_sheet", lambda sid, *a, inherited, **kw: seen.append((sid, inherited)))
    monkeypatch.setattr(search_sheet, "_hand_on", lambda *a: 0)
    monkeypatch.setattr(search_sheet, "_observe", lambda *a: None)
    sid = sheets.sheet_id_for("2")
    search_sheet.fast_pass("SUV", operator_text="a car", sheet=sid)
    from widgets.results import data as sheet_mod
    store.save(sheet_mod.sheet_key(sid), {"title": "a car", "items": []})
    search_sheet.fast_pass("SUV", operator_text="a car, big", sheet=sid)
    assert seen == [(sid, False), (sid, True)], \
        "an errand's sheet was treated as inherited before anything was in it (the box opened as a bare title)"

