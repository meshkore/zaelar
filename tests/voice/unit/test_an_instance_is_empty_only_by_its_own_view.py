"""An instance card is empty only by its OWN view (node 2.192).

Demo pass 68, S1 (2026-09-30): «so how did the monitors go, show me» brought `results::1e8adc-ls1` up with its three
monitors, and the canned ack said «I've opened it, though there's nothing in it yet.» — `nothing_to_show` read the
BARE `results` card, which was empty.
"""
from nucleo.flash import surface_ack as sa


def test_an_instance_with_rows_is_not_empty_whatever_the_base_says(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(sa, "saved_state_is_empty", lambda wid: True)
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": wid != "results::1e8adc-ls1", "items": []})
    assert sa.nothing_to_show("results::1e8adc-ls1") is False
    assert sa.nothing_to_show("results::other") is True


def test_an_unreadable_instance_never_claims_empty(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: None)
    assert sa.nothing_to_show("results::x") is False


def test_a_base_card_keeps_its_saved_state_reading(monkeypatch):
    monkeypatch.setattr(sa, "saved_state_is_empty", lambda wid: wid == "results")
    assert sa.nothing_to_show("results") is True
