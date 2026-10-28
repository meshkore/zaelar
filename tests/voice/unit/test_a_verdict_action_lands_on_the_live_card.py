"""A verdict's action brings up the LIVE card, never a bare phantom (demo passes 38/44/47, 2026-09-29, S2).

«compare them side by side» — the brief named `results:layout`; the data-op landed on the sheet
(`instances.data_target`) while the present opened an empty bare `results` card beside it, and «close the
results» then closed the phantom and left the sheet. One door narrows both halves."""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def test_a_base_id_is_presented_as_its_one_open_instance(monkeypatch):
    from nucleo.flash import direct_action as da
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["agenda", "results::18fe36-ls1"])
    assert da.card_to_present("results", "compare them side by side") == "results::18fe36-ls1"
    assert da.card_to_present("agenda", "show me tomorrow") == "agenda"


def test_a_base_with_no_instance_stays_the_base(monkeypatch):
    from nucleo.flash import direct_action as da
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["agenda"])
    assert da.card_to_present("markets", "show me the chart") == "markets"


_RUNG = {"widget": "results", "action": "layout", "payload": {"view": "side"}, "label": "compare", "source": "brief"}


def _live_sheet(monkeypatch):
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["agenda", "results::18fe36-ls1"])
    presented, applied = [], []
    return presented, applied, (lambda wid, **kw: presented.append(wid)), (lambda *a: applied.append(a))


def test_both_rungs_present_through_the_narrowing_door(monkeypatch):
    """Run both rungs (refactor2710-05: read by what they do, not by their text): the declared action that takes a
    commission's place (`take_rung`) and the verdict completing the model (`complete`) each bring up the LIVE sheet,
    never a bare `results` beside it — and the data-op itself still names the card the verdict named."""
    from nucleo.flash import direct_action as da
    from nucleo.flash import verdict_card
    presented, applied, present, apply = _live_sheet(monkeypatch)
    monkeypatch.setattr(da, "resolve", lambda *a, **k: dict(_RUNG))
    assert da.take_rung({"v": "compare them side by side", "more": []}, brief=None, operator_text="compare them side by side",
                        emit=lambda *a, **k: None, present=present, apply_widget_data=apply)
    monkeypatch.setattr(da, "from_brief", lambda brief: ("results", "layout"))
    monkeypatch.setattr(verdict_card, "canvas_yields", lambda brief: True)
    assert da.complete(None, operator_text="compare them side by side", emit=lambda *a, **k: None, present=present,
                       apply_widget_data=apply, require_order=False) == "layout"
    assert presented == ["results::18fe36-ls1", "results::18fe36-ls1"], presented
    assert [a[0] for a in applied] == ["results", "results"]
