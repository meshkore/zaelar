"""V2-472 — an amount no source of ours names does not survive a live errand.

The blocker class that dominates the US board (`market_claims_before_delivery` measures it from the
instrument side): mid-errand, with nothing to hand over yet, the model invents a market figure and says
it with the same confidence as a real one — «several 27\" 4K models under $400» (round 12, user's ceiling
was $250), «the $200–300 range is a sweet spot» (round 10), «CUNPU 27\" at $136» (round 13). The prompt
rule ("either it is in your STATE or YOU DON'T KNOW") loses one round in three; the conduct is guaranteed by code,
like every delivery rule in this family. Conservative by the same asymmetry as the instrument: the
operator's own figures are backing, the sheet's rows are backing, and with no live errand nothing is
touched — a trivia answer is not a finding.
"""
from __future__ import annotations


from nucleo.flash import delivery as D


def _strip(reply, *, user_text="", rows=(), active=True):
    return D.strip_unbacked_amounts(reply, user_text=user_text, rows=list(rows), active=active)


def test_an_invented_figure_is_cut_and_the_promise_survives():
    out, dropped = _strip(
        "The results point to several 27\" 4K models under $400. I'll pull the current prices for you.",
        user_text="I need a 27 inch 4K monitor, cheaper than $250 would be great")
    assert "$400" not in out, out
    assert "I'll pull the current prices" in out, "the sentence without the invention survives"
    assert dropped, "the cut is reported, never silent"


def test_the_operators_own_figure_is_backing():
    out, dropped = _strip("Got it — under $250, cheapest with good reviews.",
                          user_text="my ceiling is $250")
    assert "$250" in out and not dropped


def test_a_figure_the_sheet_carries_is_backing():
    out, dropped = _strip("The Dell S2725QS sits at $279.99 right now.",
                          user_text="cheapest 27 inch 4K",
                          rows=["Dell 27 Plus 4K Monitor S2725QS — $279.99"])
    assert "$279.99" in out and not dropped


def test_without_a_live_errand_nothing_is_touched():
    out, dropped = _strip("A first-class stamp runs about $0.73 these days.", active=False)
    assert "$0.73" in out and not dropped


def test_a_reply_that_would_vanish_entirely_stays_whole():
    """Fail-open: better an invented figure the judge can see than a mute turn nobody can diagnose."""
    out, dropped = _strip("Around $136 for the CUNPU.", user_text="find me a monitor")
    assert out == "Around $136 for the CUNPU.", out
    assert dropped, "…but the event still says what was seen"
