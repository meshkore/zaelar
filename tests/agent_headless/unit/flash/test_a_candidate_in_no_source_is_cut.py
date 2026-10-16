"""Node 2.689 — a sentence naming a candidate (a «title — price» quote, or a name before a price) that no source
carries is cut; one a source carries stands, and outside a shortlist the guard stays out.

search-buy-ski-gear__us (2026-10-14) was judged «Esquís Head Kore 99 … — 208.69, a candidate in no sheet row»: it WAS
a row of the sheet at that turn (a later rewrite dropped it), so it stands here; the same sentence over a sheet
without it is the invention the rule cuts. A name the notes pushed into his turn, the in-turn search or a live
errand's step carries is backed too, and his own figure («up to $250») never makes a candidate.

Disarm: `_backed_name` returning False → `test_a_candidate_a_source_carries_stands` goes red; returning True →
`test_a_candidate_on_no_sheet_and_in_no_source_is_cut` goes red.
"""
from __future__ import annotations

from ._claim_scene import SKI_KORE, review, said

GHOST = "Best pick so far: the Völkl Blaze 94 with Marker Duke bindings at $310."


def test_a_candidate_on_no_sheet_and_in_no_source_is_cut(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    r = review(GHOST + " I'll keep narrowing it down.", "anything yet?", sheets=("ski_us",))
    assert [c["why"] for c in r["cut"]] == ["candidate"] and " ".join(r["parts"]) == "I'll keep narrowing it down."


def test_a_reply_that_was_only_the_invention_says_so(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from i18n import langs
    from nucleo.flash import row_claims as R
    monkeypatch.setattr(R.B, "rows", lambda: [])
    monkeypatch.setattr(R.B, "texts", lambda *a, **k: [])
    monkeypatch.setattr(R.B, "goals", lambda: "")
    monkeypatch.setattr(R.B, "in_errand", lambda: True)
    assert R.guard(GHOST, [], "anything yet?") == langs.spec("en").claim_candidate_unbacked


def test_a_candidate_a_source_carries_stands(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert said(SKI_KORE, "San Francisco", sheets=("ski_us",)) == SKI_KORE
    note = "[SISTEMA] Aviso para el operador (zaelar): Best pick: Völkl Blaze 94 with Marker Duke bindings, $310."
    assert said(GHOST, "anything yet?", sheets=("ski_us",), evidence=(note,)) == GHOST
    search = "Völkl Blaze 94 — used, with Marker Duke bindings — $310 on Craigslist"
    assert said(GHOST, "anything yet?", sheets=("ski_us",), evidence=(search,)) == GHOST


def test_his_figure_or_a_plan_or_a_turn_outside_a_shortlist_is_no_candidate(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    plan = "I'll prepare to search for 27-inch 4K monitors up to $250, prioritizing eye comfort."
    window = [{"role": "user", "content": "Find me a 27-inch 4K monitor, up to $250."}]
    assert said(plan, "ok", sheets=("ski_us",), window=window) == plan
    answer = "Netflix Standard costs $17.99 a month in the US."
    assert said(answer, "how much is netflix?", sheets=("ski_us",), errand=False) == answer


def test_a_row_the_door_turned_away_backs_no_candidate(monkeypatch):
    """A row filed under Rejected is not on his list: a sentence offering it is the same invention as one offering a
    row no sheet ever held (audit V2-783 P1-2, 2026-10-16 — the backing units took the Rejected tab as a source)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from nucleo.flash import row_claims as R
    rejected = {"item": {"title": "Völkl Blaze 94 with Marker Duke bindings", "price": "$310"},
                "text": "Völkl Blaze 94 with Marker Duke bindings", "rejected": True}
    live = {"item": {"title": "Head Kore 99 skis", "price": "$208.69"}, "text": "Head Kore 99 skis — $208.69", "rejected": False}
    r = R.review(GHOST, [], "anything yet?", rows=[live, rejected], evidence=[], goals="", errand=True)
    assert [c["why"] for c in r["cut"]] == ["candidate"], r
    r = R.review(GHOST, [], "anything yet?", rows=[live, {**rejected, "rejected": False}], evidence=[], goals="",
                 errand=True)
    assert r["cut"] == [], "the same row on the list backs the sentence"
