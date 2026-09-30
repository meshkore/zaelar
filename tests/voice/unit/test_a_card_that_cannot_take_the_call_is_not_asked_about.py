"""A card whose declared action cannot take the call's fields is not a candidate for it (node 2.190).

Demo pass 66, M3 (2026-09-30): «and the nasdaq, over the whole year» → `markets:show {symbol, range}`, with the picture
viewer also open (a late worker had just put the wallpaper there). Both declare `show`, the verdict was unsure, and
the turn asked «Which one exactly? I have imagenes, markets.» — the viewer's `show` takes items/query, never a symbol.
"""
from nucleo.flash import frontend as fe


def test_the_viewer_is_not_asked_about_for_a_market_symbol():
    route, alt = fe.which_card("markets", "show", open_ids=["imagenes", "markets"], brief=None,
                               payload={"symbol": "^IXIC", "range": "1y"})
    assert route == "keep"


def test_without_a_payload_the_old_question_stands():
    route, alt = fe.which_card("markets", "show", open_ids=["imagenes", "markets"], brief=None)
    assert route == "ask" and len(alt) == 2


def test_two_cards_that_both_take_the_fields_still_ask():
    route, _ = fe.which_card("youtube", "play", open_ids=["youtube", "musica"], brief=None, payload={})
    assert route in ("ask", "keep")
    assert fe._takes("imagenes", "show", {"query": "ferrari"}) is True
    assert fe._takes("imagenes", "show", {"symbol": "AAPL"}) is False
    assert fe._takes("markets", "show", {"symbol": "AAPL"}) is True


def test_an_op_on_a_blank_base_card_goes_to_its_only_sibling_with_content(monkeypatch):
    """Demo pass 66, S2-S3: ops landed on the bare `results` card instead of the monitors' sheet."""
    from widgets import instances
    from nucleo import truth
    monkeypatch.setattr(instances, "card_face", lambda w: {"label": "", "blank": False})
    views = {"results": {"empty": True, "items": []}, "results::a1": {"empty": False, "items": [1, 2, 3]},
             "results::b2": {"empty": True, "items": []}}
    monkeypatch.setattr(truth, "widget_view", lambda w: views.get(w))
    assert fe.which_card("results", "layout", open_ids=["results", "results::a1", "results::b2"]) == ("card", "results::a1")
    views["results"] = {"empty": False, "items": [1]}
    assert fe._the_sibling_with_content("results", ["results", "results::a1"]) == "", "a bare card with content is its own"
    views["results"] = {"empty": True, "items": []}
    views["results::b2"] = {"empty": False, "items": [9]}
    assert fe._the_sibling_with_content("results", ["results", "results::a1", "results::b2"]) == "", "two full: no guess"
