"""V2-540 — an action from the canvas must land on the sheet the operator is LOOKING AT.

The operator, with a sheet of catamarans on screen: «el botón de ver detalle no es clic. Tengo tendencia
inmediatamente cuando veo la lista a darle a detalle porque quiero ver la ficha completa.»

The button was wired, painted and enabled. What was broken is the ADDRESS. `desktop.js::ctx.action` stamps the
open instance into every payload under the key the canvas uses everywhere — `q` — while `results.apply_action`
only ever looked for `sheet`, a key the canvas has never sent. So every click on an instantiated sheet
(`results::<errand>`, which is what a sheet born of an errand always is) was answered against the DEFAULT sheet,
found nothing there, and returned `{ok: false}` that the click handler threw away.

`view_data(q)` has read the instance out of `q` since V2-259. Only the writer never followed — which is why
READING the sheet always worked and WRITING to it never did, and why this looked like a dead button rather than
a wrong address.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    """ISOLATED store — the operator's real sheets are his work, not this test's fixture."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.results import data as rs
    rs.apply_action("present", {
        "sheet": "errand1", "title": "Catamaranes de segunda mano",
        "items": [{"title": "Lagoon 380", "price": "151.008 €"},
                  {"title": "Lagoon 400 S2", "price": "280.000 €"}]})
    return rs


def _as_the_canvas_sends_it(payload):
    """`desktop.js` builds EVERY action payload as `{...payload, q}` — never `sheet`."""
    return {**payload, "q": "errand1"}


def test_ver_detalle_opens_the_record_when_the_canvas_asks_the_way_it_actually_asks(sheet):
    """THE defect. Before the fix this came back
    `{'ok': False, 'error': 'no encuentro ese resultado en la hoja...'}` — a real refusal that no one read."""
    res = sheet.apply_action("detail", _as_the_canvas_sends_it({"title": "Lagoon 380"}))
    assert res.get("ok") is True, res
    data = sheet.view_data("errand1")
    assert data.get("view") == "detail" and data.get("focus") == "Lagoon 380", data


def test_it_is_not_only_the_detail_button_every_click_shared_the_wrong_address(sheet):
    """The mismatch was in the ONE line that resolves the sheet, so it hit every interactive action alike —
    which is why fixing it there and not in the button is the honest fix."""
    assert sheet.apply_action("choose", _as_the_canvas_sends_it({"title": "Lagoon 400 S2"})).get("ok") is True
    assert sheet.view_data("errand1").get("chosen") == "Lagoon 400 S2"
    assert sheet.apply_action("list", _as_the_canvas_sends_it({})).get("ok") is True
    assert sheet.view_data("errand1").get("view") is None


def test_the_DEFAULT_sheet_is_never_touched_by_an_instance_click(sheet):
    """The other face of the same bug: those clicks were not lost, they were LANDING somewhere — on whatever
    sheet the widget opens without an instance. Writing a stranger's `view` there is its own defect."""
    # `choose` is the one that PROVES it, and `detail` is not: detail looks the item up first, so on the wrong
    # sheet it fails and writes nothing. `choose` writes what it is told without a lookup — so with the wrong
    # address it stamped a stranger's pick onto the default sheet, silently, and the click still looked dead.
    sheet.apply_action("choose", _as_the_canvas_sends_it({"title": "Lagoon 400 S2"}))
    sheet.apply_action("detail", _as_the_canvas_sends_it({"title": "Lagoon 380"}))
    default = sheet.view_data("")
    assert default.get("items") == [], default
    assert default.get("view") is None, default
    assert default.get("chosen") in (None, ""), \
        f"an instance click wrote onto the default sheet: {default.get('chosen')!r}"


def test_an_explicit_sheet_still_wins_over_q(sheet):
    """`sheet` is what the brain sends by name; `q` is what the canvas sends by position. Both must work, and
    an explicit one must not be overridden."""
    sheet.apply_action("present", {"sheet": "errand2", "title": "Otra",
                                   "items": [{"title": "Bali 4.1"}]})
    res = sheet.apply_action("detail", {"title": "Bali 4.1", "sheet": "errand2", "q": "errand1"})
    assert res.get("ok") is True, res
    assert sheet.view_data("errand2").get("focus") == "Bali 4.1"
    assert sheet.view_data("errand1").get("view") is None, "it wrote to the sheet named by q, not by sheet"
