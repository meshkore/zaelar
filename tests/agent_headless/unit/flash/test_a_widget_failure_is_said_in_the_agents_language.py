"""Demo pass 48 (2026-09-29), V6: a YouTube play_result failed and its `message` — «No hay resultados de búsqueda ahora
mismo.», product copy written in Spanish — was spoken verbatim into an English session. The spoken line now goes
through the same composer a finished errand's line does: the agent's language, or the widget's words when the
composer cannot be reached."""
import asyncio

import pytest

from nucleo.flash import data_ops


@pytest.fixture
def heard(monkeypatch):
    said = []

    async def notify(title, text, **k):
        said.append(text)
        return True
    from voice import proactive, brain_notes
    monkeypatch.setattr(proactive, "notify", notify)
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: None)
    data_ops._DEDUP.clear() if hasattr(data_ops, "_DEDUP") else None
    return said


def test_the_failure_is_said_in_the_agents_language(heard, monkeypatch):
    from nucleo.workers import spoken_delivery as sd

    async def line(goal, summary, ok=True):
        assert "No hay resultados" in summary and ok is False
        return "There are no search results right now."
    monkeypatch.setattr(sd, "line", line)
    res = {"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."}
    assert asyncio.run(data_ops.report_failure("youtube", "play_result", res))
    assert heard == ["There are no search results right now."]


def test_without_the_composer_the_widgets_words_are_still_said(heard, monkeypatch):
    """…to a Spanish-speaking agent: widget copy is Spanish, and since demo pass 69 it is never voiced raw into
    another language (the [SISTEMA] note makes the model say it)."""
    from nucleo.workers import spoken_delivery as sd
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")

    async def line(goal, summary, ok=True):
        return ""
    monkeypatch.setattr(sd, "line", line)
    res = {"ok": False, "error": "x", "message": "No hay resultados de búsqueda ahora mismo (2)."}
    asyncio.run(data_ops.report_failure("youtube", "play_result", res))
    assert heard == ["No hay resultados de búsqueda ahora mismo (2)."]
