"""A structured value from a provider reaches the sheet as TEXT, never as its Python repr (V2-831 R9, node 4.328).

Demo pass T-19 (sandbox at b65172cca), S3 «open the best deal»: the LG monitor's record painted `{'country': 'GB'}`
under the price and `Rating {'value': 100, 'count': ` beside it. The row came from a network agent whose answer
carried `rating: {value, count}` and `location: {country}`; the producer `str()`-ed them (and cut the rating at 24
characters, mid-structure) before the sheet's door ever saw them, so the door stored Python.

The class: a value's SHAPE is not text. Two halves, both tested:
  · the producers (`nucleo/cli/mesh._rows_in`, `search.result.Candidate.to_row`) pass a structure through RAW;
  · the sheet's door (`widgets/results/record.flat`, used by every slot of `_clean_item` and by the browser
    intake) is the ONE place that flattens it — by shape, never by a provider's field names.
Variants the incident did not carry: a second provider with a differently shaped row (price object, list of
places, nested seller, a bool), and the browser intake door.
"""
from __future__ import annotations

from nucleo.cli import mesh as M
from widgets.results import clean, intake

#: The network agent's answer, shaped like the one in the demo pass (eBay finder, LG monitor).
AGENT_A = {"results": [
    {"title": "Monitor LG 27UN83A-W 27 pulgadas UHD 4K con soporte", "price": 173.43,
     "url": "https://www.ebay.es/itm/1", "rating": {"value": 100, "count": 2417}, "location": {"country": "GB"}},
]}
#: Another provider, another shape: price as an object, rating as stars in a list, the place as a nested record.
AGENT_B = {"data": {"listings": [
    {"name": "Dell S2721QS 27 4K", "amount": {"value": "289.00", "currency": "USD"},
     "link": "https://example.test/dell", "stars": [4.6, 812], "address": {"city": "Austin", "geo": {"lat": 30.2}},
     "tel": {"number": "+1 512 555 0100", "verified": True}},
]}}


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def _stored(agent: dict) -> dict:
    """The agent's answer through the real producers and the sheet's own item door."""
    rows = M._rows_in(agent)
    items = clean._clean_items(rows)
    assert len(items) == 1, items
    return items[0]


def _fact(it: dict, label: str) -> str:
    return next((f["value"] for f in it.get("facts") or [] if f["label"] == label), "")


def _no_repr(it: dict) -> None:
    bad = [s for s in _strings(it) if any(c in s for c in "{}[]'") or s in ("True", "False", "None")]
    assert not bad, f"a structure reached the sheet as its repr: {bad}"


def test_the_demo_rows_rating_and_place_are_text_and_whole(monkeypatch):
    monkeypatch.setattr("search.result._labels", lambda: {"rating": "Rating", "phone": "Phone",
                                                          "availability": "Availability", "origin": "Origin"})
    it = _stored(AGENT_A)
    _no_repr(it)
    # R9b (node 4.331): a KEYED value keeps its keys — the place is a labelled fact, never bare text by the price
    assert "subtitle" not in it and _fact(it, "Country") == "GB", it
    assert _fact(it, "Rating") == "Value 100 · Count 2417", it      # whole: it was cut mid-structure before
    assert it["price"] == "173.43"


def test_a_differently_shaped_provider_row_is_text_too(monkeypatch):
    monkeypatch.setattr("search.result._labels", lambda: {"rating": "Rating", "phone": "Phone",
                                                          "availability": "Availability", "origin": "Origin"})
    it = _stored(AGENT_B)
    _no_repr(it)
    assert it["price"] == "289.00 · USD"
    assert _fact(it, "Rating") == "4.6 · 812"
    assert "subtitle" not in it and _fact(it, "City") == "Austin" and _fact(it, "Geo") == "30.2", it
    assert _fact(it, "Phone") == "+1 512 555 0100"          # the bool beside it lends nothing


def test_the_browser_door_and_the_item_door_flatten_by_shape():
    item = intake._to_item({"title": {"text": "Sony Bravia"}, "price": {"amount": 499, "currency": "EUR"},
                            "subtitle": ["Madrid", "Centro"], "tel": 915550100, "image": {"src": "x.png"}})
    cleaned = clean._clean_item({**item, "facts": {"Size": {"in": 55}, "Seller": {"name": "Ana", "ok": True}},
                                 "lines": [{"t": "one"}, None, ["two"]], "badge": {"a": {"b": {"c": "deep"}}}})
    _no_repr(cleaned)
    assert cleaned["title"] == "Sony Bravia" and cleaned["price"] == "499 · EUR"
    assert cleaned["subtitle"] == "Madrid · Centro" and cleaned["image"] == "x.png"
    assert {"label": "Size", "value": "55"} in cleaned["facts"]
    assert {"label": "Seller", "value": "Ana"} in cleaned["facts"]
    assert cleaned["lines"] == ["one", "two"]
    assert "badge" not in cleaned and {"label": "A", "value": "deep"} in cleaned["facts"]   # keyed → a fact (R9b)
