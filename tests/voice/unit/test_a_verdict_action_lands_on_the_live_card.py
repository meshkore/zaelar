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


def test_both_rungs_present_through_the_narrowing_door():
    src = (ENGINE / "nucleo/flash/direct_action.py").read_text(encoding="utf-8")
    assert src.count('present(card_to_present(rung["widget"], operator_text), reason="turn-order"') == 2
    assert 'present(rung["widget"], reason="turn-order"' not in src
