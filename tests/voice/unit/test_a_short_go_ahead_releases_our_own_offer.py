"""«Do it» after our offer resumes the offered errand's ROW; it is never read from words shared with our line (node 2.920).

Live, 2026-10-28 17:49 (T28): we had said «…the results don't explicitly confirm the Spain release, though it's listed
as the same Paramount+ Premium date, so I can dig into that specifically if you want.» He said «d oit». The model
proposed «Check for Richard (living in Spain) where and when Dexter: Resurrection Season 2…» and the fragment guard
annulled it because our offer carried no question mark (`answered_an_offer`). The reply was «Sorry, I didn't follow».

The first fix counted content words shared by our line and the model's errand (`prior_line.restates_our_offer`): any
paraphrase failed it and any stranger sharing two long words passed it. V2-831 T-07 deleted it. The identity is the
pending row the offer is about: the turn's verdict over the pending rows (`resume_turn.before_fragment_guard`, our
previous line in its criteria) runs before the guard, and the row it picks resumes from itself — the model's text,
whatever it says, is replaced by that resumption. With no row picked, a bare go-ahead is still a fragment.

Open (T-07b): an offer made by an INLINE turn opens no request row and parks no offer, so «do it» after it has nothing
to resume — the T28 shape itself. Kept as a strict xfail naming that class.

Disarm: with `before_fragment_guard` not consulting the rows (returns at once), the first two tests go red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import jev, pending_work
from nucleo.acts import errand as _errand
from nucleo.flash import escalation_guard, resume_turn

OFFER = ("Got it — let me check where Dexter: Resurrection Season 2 will actually be available in Spain. The results "
         "don't explicitly confirm the Spain release, so I can dig into that specifically if you want.")
ERRAND = "Check for Richard (living in Spain) where and when Dexter: Resurrection Season 2 will be available"

DEXTER = {"id": "boot-9f15b8-1", "source": "task", "title": "Verify where Dexter: Resurrection S2 streams in Spain",
          "state": "done", "brief": "Verify, for a user in Spain, where Dexter: Resurrection S2 streams",
          "outcome": "Paramount+ listed, Spain unconfirmed", "sheet": "results::9f15b8-1", "surface": "results",
          "kind": "web", "at": 1.0}
HOTEL = {"id": "boot-77aa-2", "source": "task", "title": "Hotel near Plaza Mayor, Salamanca, 2 nights",
         "state": "done", "brief": "Find a hotel near Plaza Mayor in Salamanca for two nights", "outcome": "3 options",
         "sheet": "results::77aa-2", "surface": "results", "kind": "web", "at": 2.0}


@pytest.fixture
def world(monkeypatch):
    """Pending rows, the verdict's pick (a stand-in for `jev.select_many` that records what it was shown) and the
    portal every resumption crosses."""
    resume_turn.reset()
    state = {"rows": [], "pick": None, "criteria": [], "resumed": []}
    monkeypatch.setattr(pending_work, "rows", lambda now=None: list(state["rows"]))

    def select_many(rows, criteria, key=None, label=None):
        state["criteria"].append(criteria)
        return [{"candidate": r} for r in rows if r["id"] == state["pick"]]

    monkeypatch.setattr(jev, "select_many", select_many)
    monkeypatch.setattr(_errand, "escalate_to_slowbrain",
                        lambda brief, context=None: state["resumed"].append((brief, dict(context or {}))) or 1)
    yield state
    resume_turn.reset()


def _turn(operator_text: str, last_reply: str, errand: str) -> dict:
    """The two doors in the order the turn crosses them (`post_stream_acts`): the rows first, then the guard."""
    req, acted = {"v": errand, "more": []}, {"widget": False}
    asyncio.run(resume_turn.before_fragment_guard(req, operator_text=operator_text, brief=None, last_reply=last_reply,
                                                  apply_widget_data=None, emit=None, acted=acted))
    annulled = escalation_guard.drop_if_fragment(req, operator_text=operator_text, brief=None, last_reply=last_reply)
    return {**req, "acted": acted["widget"], "annulled": annulled}


def test_a_typo_go_ahead_resumes_the_row_our_offer_is_about(world):
    world["rows"], world["pick"] = [HOTEL, DEXTER], DEXTER["id"]
    out = _turn("d oit", OFFER, ERRAND)
    assert out["resumed"] == [DEXTER["id"]] and out["acted"] and not out["annulled"]
    assert world["resumed"][0][1]["task_uid"] == DEXTER["id"]           # the SAME row resumes, not a new errand
    assert OFFER[:60] in world["criteria"][0]                           # the verdict saw our line


def test_another_language_and_domain_resume_their_own_row(world):
    world["rows"], world["pick"] = [HOTEL, DEXTER], HOTEL["id"]
    offer = "Tengo tres hoteles cerca de la Plaza Mayor; si quieres, miro cuál tiene parking."
    out = _turn("vale", offer, "Mira qué hotel de Salamanca tiene parking")
    assert out["resumed"] == [HOTEL["id"]] and not out["annulled"]
    assert world["resumed"][0][1]["task_uid"] == HOTEL["id"]


def test_a_go_ahead_that_means_no_pending_row_is_still_a_fragment(world):
    world["rows"], world["pick"] = [HOTEL, DEXTER], None                # the verdict: his turn means none of them
    out = _turn("d oit", OFFER, "Book a table for two at a sushi place tonight")
    assert out["annulled"] and out["v"] is None and not world["resumed"]


def test_the_model_text_never_outranks_the_row(world):
    """A stranger errand the model writes over a go-ahead is replaced by the row the verdict picked."""
    world["rows"], world["pick"] = [DEXTER], DEXTER["id"]
    out = _turn("d oit", OFFER, "Order groceries for the week")
    assert out["v"] is None and out["resumed"] == [DEXTER["id"]]
    assert "groceries" not in world["resumed"][0][0].lower()


@pytest.mark.xfail(strict=True, reason="an inline offer opens no request row (V2-831 T-07b): «do it» after it has "
                                       "no row to resume, so the commission is annulled as a fragment")
def test_do_it_after_an_inline_offer_resumes_what_was_offered(world):
    world["rows"], world["pick"] = [], None                              # T28: the offer came from an inline search turn
    out = _turn("d oit", OFFER, ERRAND)
    assert not out["annulled"]
