"""The results sheet's digest — read by the brain every turn the sheet is open — is in the INSTANCE's language
(V2-831): it was Spanish in every session, so an English turn reasoned over «FUENTES», «descartados», «hoja VACÍA»
and the instructions inside it. Its prose now comes from the `ui` pack (`results.digest.*`), English floor.

Disarm: make `digest._t` ignore the language table → the Spanish case reds.
"""
from __future__ import annotations

_SHEET = {"summary": {"explored": 30, "discarded": 27}, "counts": {"shown": 3},
          "sources": [{"name": "Best Buy", "status": "blocked"}],
          "items": [{"title": "Dell S2725QC", "price": "$299", "url": "https://x"}]}


def test_an_english_instance_reads_its_sheet_in_english(monkeypatch):
    from i18n import runtime
    from widgets.results import digest
    monkeypatch.setattr(runtime, "active_code", lambda: "en")
    text = digest.one(_SHEET)
    assert "SOURCES (1)" in text and "27 discarded" in text and "blocked access" in text, text
    assert "FUENTES" not in text and "descartados" not in text


def test_a_spanish_instance_reads_it_in_spanish(monkeypatch):
    from i18n import runtime
    from widgets.results import digest
    monkeypatch.setattr(runtime, "active_code", lambda: "es")
    text = digest.one(_SHEET)
    assert "FUENTES (1)" in text and "27 descartados" in text and "bloqueó el acceso" in text, text
