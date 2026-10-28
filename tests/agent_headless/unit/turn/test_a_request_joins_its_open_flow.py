"""A request joins the open flow it belongs to BEFORE anything is opened (V2-784, 2026-10-21).

The operator's demo pass, 19:23: «…twenty seven inch four k monitors?» launched a listing hunt; he kept talking,
that turn was cancelled, but the hunt ran on in its thread and was nobody's flow yet. «…Under four hundred bucks…
show me when we got them» arrived 8 s later, found nothing open, and launched a second hunt with a second sheet.
The dispatcher's dedup later folded the second WORKER into the first and left the second SHEET open forever.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.acts import search_listing
from nucleo.turn import flow_of, launches

FRAGMENT = "Okay. Can you find me, like, three twenty seven inch four k monitors?"
WHOLE = ("Okay. Can you find me, like, three twenty seven inch four k monitors? Under four hundred bucks. "
         "Or so, So show me when we got them.")
REQ = {"query": "27 inch 4K monitor"}


@pytest.fixture
def hunts(monkeypatch):
    """`run` replaced by a recorder; the first call blocks like a hunt still on the network."""
    launches.reset()
    calls, gate = [], threading.Event()

    def fake_run(query, **kw):
        calls.append(kw)
        if len(calls) == 1:
            gate.wait(5)
        return {"delivered": False, "n": 0, "sheet": kw.get("sheet") or kw.get("new_sheet"), "escalated": 0,
                "reason": "", "ctx": ""}

    monkeypatch.setattr(search_listing, "fast_pass", fake_run)
    monkeypatch.setattr(search_listing, "FAST_PASS_BUDGET_S", 0.3)
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", lambda text, live: "")
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [])
    monkeypatch.setattr("nucleo.flash.escalate.pending", lambda: [])
    yield calls
    gate.set()
    launches.reset()


def test_the_sentence_that_finishes_a_cancelled_fragment_reuses_its_sheet(hunts):
    async def scene():
        first = asyncio.ensure_future(search_listing.listings({"text": FRAGMENT}, REQ))
        await asyncio.sleep(0.05)
        first.cancel()                               # he kept talking: the fragment's turn is cancelled
        await asyncio.sleep(0.05)
        await search_listing.listings({"text": WHOLE}, REQ)

    asyncio.run(scene())
    assert len(hunts) == 2
    sheet = hunts[0]["new_sheet"]
    assert sheet, "the first hunt had no sheet of its own from the start"
    assert hunts[1]["sheet"] == sheet and not hunts[1]["new_sheet"], \
        "the whole sentence opened a SECOND sheet beside the hunt it finishes"


def test_a_request_about_a_live_worker_is_injected_not_hunted_again(hunts, monkeypatch):
    sent = []

    async def fake_inject(which, message):
        sent.append((which, message))
        return [which]

    monkeypatch.setattr("nucleo.dispatch.pending_summaries",
                        lambda: [{"id": "7", "request": FRAGMENT, "sheet": "S7"}])
    monkeypatch.setattr("nucleo.dispatch.get_record", lambda tid: None)
    monkeypatch.setattr("nucleo.dispatch.inject", fake_inject)
    _o = asyncio.run(search_listing.listings({"text": WHOLE}, REQ))
    res, _ = _o.data, _o.say
    assert sent == [("7", WHOLE)] and not hunts, "the refinement started a second hunt beside the live worker"
    assert res["joined"] == "7" and res["sheet"] == "S7"


def test_a_word_about_the_weather_in_between_does_not_hide_the_hunt(hunts, monkeypatch):
    """The candidates are every open flow, not the last trace; a refinement with few shared words goes to the
    model judge, the same one the dispatcher uses."""
    launches.opened(FRAGMENT, "S1")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand",
                        lambda text, live: next(i for i, g in live if "monitors" in g))
    flow = asyncio.run(flow_of.flow_of("Actually make them cheaper, under 350"))
    assert flow and flow["sheet"] == "S1"


def test_a_new_hunt_is_a_new_flow(hunts, monkeypatch):
    launches.opened(FRAGMENT, "S1")
    assert asyncio.run(flow_of.flow_of("find me a used acoustic guitar in Madrid")) is None


# ── F3/F4 · the dispatcher's late fold is an alarm, and it no longer leaves a sheet behind ──────────────────

def test_a_late_fold_closes_the_duplicates_sheet_and_says_so(monkeypatch):
    from types import SimpleNamespace

    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr("nucleo.dispatch.get_record", lambda tid: SimpleNamespace(sheet="ls1"))
    monkeypatch.setattr("nucleo.dispatch.sheet_of", lambda rec: rec.sheet)
    assert flow_of.late_fold("7", {"sheet": "ls2"}) == "ls2"
    assert any(a[:2] == ("widget", "close") and kw["extra"]["id"] == "results::ls2" for a, kw in seen), \
        "the folded duplicate's sheet stayed on screen with nobody writing into it"
    assert any(a[0] == "alert" for a, _ in seen), "a late fold means the flow door missed — it must be SAID"


def test_a_late_fold_into_the_same_sheet_closes_nothing(monkeypatch):
    from types import SimpleNamespace

    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr("nucleo.dispatch.get_record", lambda tid: SimpleNamespace(sheet="ls1"))
    monkeypatch.setattr("nucleo.dispatch.sheet_of", lambda rec: rec.sheet)
    assert flow_of.late_fold("7", {"sheet": "ls1"}) == ""
    assert not any(a[:2] == ("widget", "close") for a, _ in seen)


def test_the_dispatchers_fold_runs_the_late_fold_with_the_escalation_context(monkeypatch):
    from nucleo import dispatch_listener as _dl
    got = []

    async def fake_inject(which, message):
        return [which]

    monkeypatch.setattr("nucleo.dispatch.inject", fake_inject)
    monkeypatch.setattr(_dl, "_close_folded", lambda key: None)
    monkeypatch.setattr(flow_of, "late_fold", lambda target, ctx: got.append((target, ctx)) or "")
    asyncio.run(_dl._fold_into("7", "under 400", "k1", {"sheet": "ls2"}))
    assert got == [("7", {"sheet": "ls2"})], "the fold dropped the escalation's sheet again"
