"""When `reopen_task` finds no errand, the results sheet the phrase names by its title is the one shown (pass 89, S1).

«show me the monitors» found no candidate at that instant (the errand's row was still settling) and the turn said
«bringing back those monitors» over an empty screen; the monitors sheet was there all along.
"""
from __future__ import annotations

from nucleo.flash import task_recall as TR


def test_no_errand_but_a_sheet_that_shares_his_words_is_shown(monkeypatch):
    from widgets.results import sheet_names as SN
    monkeypatch.setattr(TR, "recall_and_reopen", lambda q: {"ok": False, "ask": []})
    monkeypatch.setattr(SN, "recent_faces", lambda limit=5: [
        {"id": "results::ab-4", "label": "5-day warm trip for Richard and Anna"},
        {"id": "results::ab-ls1", "label": "Three 27-inch 4K monitors under $400"}])
    v = TR.voice_turn("27-inch 4K monitors under $400")
    assert v["show"] == "results::ab-ls1"


def test_a_tie_or_a_single_shared_word_shows_nothing(monkeypatch):
    from widgets.results import sheet_names as SN
    monkeypatch.setattr(TR, "recall_and_reopen", lambda q: {"ok": False, "ask": []})
    monkeypatch.setattr(SN, "recent_faces", lambda limit=5: [
        {"id": "results::a", "label": "Monitors for the office"}, {"id": "results::b", "label": "Monitors at home"}])
    assert TR.voice_turn("monitors")["show"] is None
