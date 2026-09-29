"""Demo pass 47 (2026-09-29), C1: the agenda's digest labelled tomorrow «(mañana, miércoles)» in an English session,
and the reply opened «Okay… mañana miércoles 30 you've got three things». How far a date is — today, tomorrow, the
weekday — is written in the language the agent speaks, from that language's own catalog."""
import pytest

from i18n import langs
from widgets.agenda import index


@pytest.mark.parametrize("code, tomorrow, later", [
    ("en", " (tomorrow, Wednesday)", " (Saturday, in 4 days)"),
    ("es", " (mañana, miércoles)", " (sábado, en 4 días)"),
])
def test_the_relative_day_is_in_the_agents_language(monkeypatch, code, tomorrow, later):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))
    assert index._day_label("2026-09-30", "2026-09-29") == tomorrow
    assert index._day_label("2026-10-03", "2026-09-29") == later
