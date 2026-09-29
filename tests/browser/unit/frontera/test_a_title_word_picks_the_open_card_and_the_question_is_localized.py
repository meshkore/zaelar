"""A word of a card's title picks it among the open ones, and the «which card?» question is in his language
(node 4.238).

Demo pass 62, S1 (2026-09-29): «so how did the monitors go, show me» with two result sheets open — «27-inch 4K
monitors under $400» and the bare one — came back as «Tienes 2 abiertas: ¿cuál te enseño…?», in Spanish, to an
English operator. The phrase named the sheet by its title («monitors»); a CLOSED sheet was already chosen that way
(`_closed_card_for`), an open one was not. And the two questions of `widgets/instances.py` were Spanish literals.
"""
import pytest

from widgets import instances as I

OPEN = ["results::2adbe5-ls1", "results"]
LABELS = {"results::2adbe5-ls1": "27-inch 4K monitors under $400", "results": "results",
          "results::aaaa-1": "Hotels in Lisbon", "results::bbbb-1": "Flights to Lisbon"}


@pytest.fixture
def cards(monkeypatch):
    monkeypatch.setattr(I, "_label", lambda wid: LABELS.get(wid, wid))
    monkeypatch.setattr(I, "_with_something_to_show", lambda ids: list(ids))
    monkeypatch.setattr(I, "instances_of", lambda tid, open_ids: [w for w in open_ids if w.split("::")[0] == tid])


def _lang(monkeypatch, code):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))


def test_a_title_word_picks_the_open_sheet_to_show_and_to_close(cards):
    got = I.resolve_show("results", OPEN, "so how did the monitors go, show me")
    assert got["id"] == "results::2adbe5-ls1" and not got["ask"]
    got = I.resolve_close("results", OPEN, "close the monitors")
    assert got["ids"] == ["results::2adbe5-ls1"] and not got["ask"]


def test_a_word_shared_by_two_titles_still_asks_in_english(cards, monkeypatch):
    _lang(monkeypatch, "en")
    both = ["results::aaaa-1", "results::bbbb-1"]
    got = I.resolve_show("results", both, "show me lisbon")
    assert got["id"] is None and got["ask"].startswith("You have 2 open: which one should I show")
    assert "«Hotels in Lisbon» or «Flights to Lisbon»" in got["ask"]
    got = I.resolve_close("results", both, "close lisbon")
    assert got["ask"].startswith("You have 2 open: which one should I close")


def test_spanish_keeps_its_question(cards, monkeypatch):
    _lang(monkeypatch, "es")
    got = I.resolve_show("results", ["results::aaaa-1", "results::bbbb-1"], "enséñame lisboa")
    assert got["ask"] == "Tienes 2 abiertas: ¿cuál te enseño, «Hotels in Lisbon» o «Flights to Lisbon»?"
