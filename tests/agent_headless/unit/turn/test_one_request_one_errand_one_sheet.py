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
def test_every_fragment_of_a_parked_request_joins_it_and_relaunches_nothing(scene, first, fragments):
    calls, judge = scene
    parked = _park("2", first)
    judge["id"] = "2"            # the house judge's verdict (lexical containment or the model): this IS errand 2
    outs = [asyncio.run(search_listing.listings({"text": text}, REQ)) for text in fragments]
    assert not calls, "a fragment of the parked request launched a hunt (and a sheet) of its own"
    assert parked["refinements"] == fragments[-5:], "his words did not reach the parked errand"
    assert all(o.verdict == "asked" and o.say == "¿Lo hago?" for o in outs), "the turn did not ask the question again"
    assert not parked["sheet"], "nothing was relaunched, so no box was opened for it"


def test_the_measured_fragment_is_proposed_by_containment_and_decided_by_the_judge(scene):
    """S4 measured: the joined fragment contains the parked request's words. Since V2-844 F2 (M2) a likeness only
    PROPOSES a parked errand: folding into it is the model judge's call — «a hotel in Paris» is not the parked Rome."""
    calls, judge = scene
    _park("2", CAR_EN[0])
    text = "let's let's focus on the car. I wanna buy a car. A new car. One of those big runners."
    assert asyncio.run(flow_of.flow_of(text)) is None, "a likeness folded a request into a parked errand by itself"
    judge["id"] = "2"
    flow = asyncio.run(flow_of.flow_of(text))
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
    assert confirm._PENDING_CONFIRM["2"].get("refinements") is None, "the guitar was folded into the car"


def test_a_new_flow_names_its_sheet_after_the_errand_it_hands_on_to(scene):
    calls, _judge = scene
    asyncio.run(search_listing.listings({"text": "find me a used acoustic guitar in Barcelona"}, REQ))
    eid = calls[0]["errand_id"]
    assert eid and calls[0]["new_sheet"] == sheets.sheet_id_for(eid), \
        "a new hunt's sheet is a counter of its own, not the errand it hands on to"


# ── S2 · the reserved id is the errand's; an unreserved escalation is unchanged ──────────────────────────────

@pytest.fixture
def portal(monkeypatch):
    from nucleo.acts import errand
    errand.reset()
    sent: list = []
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: sent.append((topic, payload)))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **kw: True)
    yield errand, sent
    errand.reset()


def test_a_born_errand_is_the_one_that_hands_on(portal, monkeypatch):
    errand, sent = portal
    monkeypatch.setattr("nucleo.circuit.ledger.born", lambda tid, req, ctx=None: f"b1-{tid}")
    tid, uid = errand.born("find me a used acoustic guitar in Barcelona")      # V2-844 F1a: born, not reserved
    assert errand.escalate_to_slowbrain("find me a used acoustic guitar in Barcelona", task_id=tid,
                                        context={"born_uid": uid}) == tid
    assert [p["id"] for t, p in sent if t == "escalate.requested"] == [tid]


def test_an_unreserved_escalation_takes_the_next_id_as_before(portal):
    errand, sent = portal
    first = errand.escalate_to_slowbrain("find me a used acoustic guitar in Barcelona")
    second = errand.escalate_to_slowbrain("book a table for two in Seville tonight")
    assert (first, second) == (1, 2)


def test_a_new_hunt_hands_on_under_the_id_its_sheet_carries(monkeypatch):
    from nucleo.acts import errand
    errand.reset()
    handed: list = []
    monkeypatch.setattr("search.listing.search", lambda q: {"items": [], "sources": [], "needs_browser": True})
    monkeypatch.setattr(search_sheet, "_write_sheet", lambda *a, **kw: None)
    monkeypatch.setattr(search_sheet, "_observe", lambda *a: None)
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda req, context=None, task_id=0: handed.append((context["sheet"], task_id)) or task_id)
    out = search_sheet.fast_pass("acoustic guitar", operator_text="a used acoustic guitar")
    assert handed == [(out["sheet"], out["escalated"])] and out["sheet"] == sheets.sheet_id_for(out["escalated"]), \
        "the hunt's worker runs under another id than the sheet it inherits"
    errand.reset()


def test_the_errands_own_filled_sheet_is_never_opened_fresh(monkeypatch, tmp_path):
    """The fast pass filled the errand's sheet under its reserved id; the worker that inherits it must not wipe it."""
    from types import SimpleNamespace

    from widgets import store
    from widgets.results import data as sheet_mod
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    opened: list = []
    monkeypatch.setattr(sheet_mod, "begin_task", lambda title, fresh=True, sheet="": opened.append((sheet, fresh)))
    mine = sheets.sheet_id_for("7")
    store.save(sheet_mod.sheet_key(mine), {"title": "a guitar", "items": [{"title": "Yamaha FG800"}]})
    rec = SimpleNamespace(task_id="7", sheet=mine, uid="", goal="a guitar", title="", label="", heard="", brief="")
    sheets._sheet_open(rec, show=False)
    assert opened == [(mine, False)], "the worker wiped the rows its own fast pass had already delivered"


# ── S3 · a launch folded into a parked errand (another door's escalation) never leaves its box behind ─────

def _fold(monkeypatch, parked_sheet: str, own: str) -> list:
    from nucleo.dispatch import listener
    from voice import observer
    seen: list = []
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(listener, "_close_folded", lambda key, ctx=None: None)
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



