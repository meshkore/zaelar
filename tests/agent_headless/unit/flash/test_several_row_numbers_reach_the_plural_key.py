"""«Quita los tres últimos» — several row numbers reach the action's plural key (refactor2710-01, bank case v2-756).

The `youtube` manifest declares `remove` with `item` (one row) AND `items` («4,5,6»). The model put «4,5,6» in `item`;
the resolver read it as ONE reference, found no row called «4,5,6» and asked «which one exactly?» over a list of six.
Several numbers that are all rows of the card now go to the declared plural key; a number that is not a row, or an
action that declares no plural key, keeps the single-row resolution.

Disarm: return "" at the top of `refs._several_rows` → the first test asks again.
"""
from widgets import refs

ROWS = [{"id": str(i), "label": f"{i}. Starship Flight {i}", "field": "item"} for i in range(1, 7)]
SPEC = {"actions": {"remove": {"payload": {"item": "1-N", "items": "4,5,6"}, "ref": "item"},
                    "play_item": {"payload": {"item": "1-N"}, "ref": "item"}}}


def _resolve(monkeypatch, action, ref):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: ROWS)
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda wid: True, raising=False)
    monkeypatch.setattr(refs.runtime, "get", lambda wid: SPEC)
    return refs.resolve("youtube", action, ref, {"item": ref})


def test_three_row_numbers_go_to_the_plural_key(monkeypatch):
    r = _resolve(monkeypatch, "remove", "4,5,6")
    assert r.ok and r.payload.get("items") == "4,5,6" and "item" not in r.payload, (r.ok, r.needs, r.payload)


def test_a_number_that_is_no_row_still_asks(monkeypatch):
    r = _resolve(monkeypatch, "remove", "4,5,9")
    assert not r.ok


def test_an_action_without_a_plural_key_resolves_one_row(monkeypatch):
    r = _resolve(monkeypatch, "play_item", "4,5")
    assert not r.payload.get("items") if r.ok else True
