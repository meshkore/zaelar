"""A keyed structure keeps its keys as LABELS — never bare text beside a value (V2-831 R9b, node 4.331).

Demo pass T-19 pass 2, S1: the agent said «the piXL at 144.71 GB». The network row carried `location: {country: GB}`;
R9 flattened it into the subtitle as a bare «GB», which the card paints under the price and the model's digest prints
on the line after `#1 piXL — 144.71`, so the model read it as the price's unit. The class: a slot every reader shows
with NO label of its own (subtitle, badge) never takes a keyed structure as bare text — each leaf becomes a fact
labelled by the key it came from (the pack's `widgets.results.field_<key>` when declared, else the key made readable);
a fact whose value has several keyed leaves keeps those keys too. A list has no keys and stays text.
Checked on what the MODEL reads (`digest.one`), not only on the stored item. Also: the phone fact's label comes from
the language pack, not a Spanish literal in the browser intake.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.cli import mesh as M
from widgets.results import clean, digest, intake

PIXL = {"results": [{"title": "Google Pixel 8 128GB", "price": 144.71, "url": "https://www.ebay.co.uk/itm/9",
                     "location": {"country": "GB"}, "rating": {"value": 99.1, "count": 5}}]}


def _fact(it: dict, label: str) -> str:
    return next((f["value"] for f in it.get("facts") or [] if f["label"] == label), "")


def test_a_keyed_place_is_a_labelled_fact_on_the_sheet_and_in_what_the_model_reads():
    items = clean._clean_items(M._rows_in(PIXL))
    it = items[0]
    assert "subtitle" not in it, it
    assert _fact(it, "Country") == "GB"
    assert _fact(it, "Rating") == "Value 99.1 · Count 5"
    seen = digest.one({"items": items}).splitlines()
    assert not [ln for ln in seen if ln.strip() == "GB"], seen          # no bare value on its own line
    assert any(ln.strip() == "- Country: GB" for ln in seen), seen
    assert any(ln.startswith("#1 ") and ln.endswith("— 144.71") for ln in seen), seen


def test_another_shape_badge_and_subtitle_lend_labelled_facts_and_a_list_stays_text():
    it = clean._clean_item({"title": "Flat in Gràcia", "price": "1.200 €", "badge": {"seller": {"name": "Ana"}},
                            "subtitle": {"zip_code": "08012", "city": "Barcelona"}})
    assert "badge" not in it and "subtitle" not in it, it
    assert _fact(it, "Seller") == "Ana" and _fact(it, "Zip code") == "08012" and _fact(it, "City") == "Barcelona"
    listed = clean._clean_item({"title": "Café", "subtitle": ["Madrid", "Centro"]})
    assert listed["subtitle"] == "Madrid · Centro" and "facts" not in listed


def test_a_label_the_pack_declares_wins_over_the_key(monkeypatch):
    from i18n import runtime as rt
    real = rt.text
    monkeypatch.setattr(rt, "text", lambda key, default="", code=None:
                        "País" if key == "widgets.results.field_country" else real(key, default, code))
    it = clean._clean_item({"title": "Pixel", "subtitle": {"country": "GB"}})
    assert _fact(it, "País") == "GB", it


@pytest.mark.parametrize("code", ["en", "es"])
def test_the_browser_intakes_phone_label_is_the_packs(monkeypatch, code):
    monkeypatch.setattr(langs, "current_code", lambda: code)
    want = langs.words("search.fact_labels", code=code)["phone"]
    item = intake._to_item({"title": "Fontanería Ruiz", "tel": "+34 600 000 000"})
    assert item["facts"][0] == {"label": want, "value": "+34 600 000 000"}, (code, item)
