"""`search-buy-surfboard__us` (2026-10-11 20:11): an English round was handed «Me he quedado sin cuota… vuelve a las
20:25» — `providers.exhausted_reason()` was a Spanish literal. It now comes from the language table, hour included."""
import time

import pytest

from nucleo.workers import providers


@pytest.mark.parametrize("code,word", [("en", "quota"), ("es", "cuota")])
def test_the_asleep_reason_is_in_the_session_language_with_the_hour(monkeypatch, code, word):
    until = time.time() + 900
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    monkeypatch.setattr(providers, "exhausted_until", lambda: until)
    said = providers.exhausted_reason()
    assert word in said and time.strftime("%H:%M", time.localtime(until)) in said
    if code == "en":
        assert "cuota" not in said


def test_an_awake_chain_has_no_reason(monkeypatch):
    monkeypatch.setattr(providers, "exhausted_until", lambda: 0.0)
    assert providers.exhausted_reason() == ""
