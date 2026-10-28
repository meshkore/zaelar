"""When `reopen_task` finds no errand, the results sheet the phrase names by its title is the one shown (pass 89, S1).

«show me the monitors» found no candidate at that instant (the errand's row was still settling) and the turn said
«bringing back those monitors» over an empty screen; the monitors sheet was there all along.
"""
from __future__ import annotations

from nucleo.turn import task_recall as TR


def test_no_errand_but_a_sheet_that_shares_his_words_is_shown(monkeypatch):
    from widgets.results import sheet_names as SN
    monkeypatch.setattr(TR, "recall_and_reopen", lambda q, *a: {"ok": False, "ask": []})
    monkeypatch.setattr(SN, "recent_faces", lambda limit=5: [
        {"id": "results::ab-4", "label": "5-day warm trip for Richard and Anna"},
        {"id": "results::ab-ls1", "label": "Three 27-inch 4K monitors under $400"}])
    v = TR.voice_turn("27-inch 4K monitors under $400")
    assert v["show"] == "results::ab-ls1"


def test_a_tie_or_a_single_shared_word_shows_nothing(monkeypatch):
    from widgets.results import sheet_names as SN
    monkeypatch.setattr(TR, "recall_and_reopen", lambda q, *a: {"ok": False, "ask": []})
    monkeypatch.setattr(SN, "recent_faces", lambda limit=5: [
        {"id": "results::a", "label": "Monitors for the office"}, {"id": "results::b", "label": "Monitors at home"}])
    assert TR.voice_turn("monitors")["show"] is None


def test_one_sheet_is_named_by_a_word_of_his_it_carries_and_never_by_none(monkeypatch):
    """The sheets are read by the SAME chooser as the errands (refactor2710-08 T-03): a lone candidate needs one word of
    his that its name carries — «the monitors» over the one monitors sheet — and a sentence that names nothing of it
    brings nothing back."""
    from widgets.results import sheet_names as SN
    monkeypatch.setattr(TR, "recall_and_reopen", lambda q, *a: {"ok": False, "ask": []})
    monkeypatch.setattr(SN, "recent_faces", lambda limit=5: [{"id": "results::m", "label": "Three monitors under $400"}])
    assert TR.voice_turn("show me the monitors")["show"] == "results::m"
    assert TR.voice_turn("what time is it")["show"] is None
