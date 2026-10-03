"""`imagenes:show` with no pictures is the picture SEARCH, whatever the viewer holds now (demo pass 82, I1).

«show me a red ferari f40»: the model called the viewer's own `show` with no items; the viewer still held the
nebula photos of B1, so the empty-viewer rule did not apply, the card answered «no llegó ninguna imagen», the
correction repeated the call, and the next order («a few more of those») went to the monitors.
"""
from nucleo.flash import card_commission as CC


def test_a_show_with_no_pictures_is_a_search_with_his_words():
    got = CC.picture_search_for_empty_show("imagenes", "show", {}, "show me a red ferari f40")
    assert got and got["query"] == "show me a red ferari f40" and got["more"] is False


def test_the_models_query_wins_over_his_sentence():
    got = CC.picture_search_for_empty_show("imagenes", "add", {"query": "red Ferrari F40"}, "a few more of those")
    assert got["query"] == "red Ferrari F40" and got["more"] is True


def test_a_show_that_carries_pictures_or_another_action_or_card_is_left_alone():
    assert CC.picture_search_for_empty_show("imagenes", "show", {"items": [{"url": "x"}]}, "x") is None
    assert CC.picture_search_for_empty_show("imagenes", "next", {}, "next one") is None
    assert CC.picture_search_for_empty_show("results", "show", {}, "show me") is None


def test_the_commission_pass_is_told_the_verdicts_action_on_its_card():
    """Demo passes 88/89, R3: the verdict read agenda:find_free and the commission pass, not told, called show_day."""
    from nucleo.flash import act_repair as AR
    manifest = {"actions": {"find_free": {}, "show_day": {}}}
    assert "«find_free»" in AR._verdict_hint("find_free", manifest)
    assert AR._verdict_hint("book_it", manifest) == "", "an undeclared action is never suggested"
    assert AR._verdict_hint("", manifest) == ""
