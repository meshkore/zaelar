#
# test_a_finished_errand_is_said_briefly_in_the_agents_language.py — demo pass 36 (2026-09-29).
#
# The monitor errand's closing summary — a full report with headings and bold, written in Spanish — was read
# out verbatim into an English session: about two and a half minutes of monologue, and the next two replies
# came out a turn late. The summary is for the sheet and the brain; the voice says what came of it, briefly,
# in the language the personal agent was set up in.
#
import asyncio
import types

import pytest

from nucleo.workers import session as ws
from nucleo.workers import spoken_delivery as sd

_REPORT = ("Hecho — las tres selecciones están en pantalla y completamente verificadas.\n\n**Lo que encontré "
           "(todos de 27\", 4K):**\n\n1. **Dell S2725QS** — 299,99 $ en Dell. " + "Detalle largo. " * 60)


@pytest.fixture
def world(monkeypatch):
    said, asked = [], []

    async def notify(title, text, **k):
        said.append(text)
        return True
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", notify)

    class _Client:
        async def complete(self, messages, **k):
            asked.append(messages)
            return "Your monitors are ready — the Dell S2725QS at $299.99 is the best pick."
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _Client)
    import nucleo.errand_title as et
    monkeypatch.setattr(et, "_spec_for_naming", lambda: object())
    import i18n.langs as langs
    monkeypatch.setattr(langs, "current_language", lambda: types.SimpleNamespace(name="English", native="English"))
    monkeypatch.setattr(ws, "operator_safe_summary", lambda s: s)
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: None)
    monkeypatch.setattr(brain_notes, "retract", lambda *a, **k: True)
    return said, asked


def _deliver():
    rec = ws.SessionRecord(task_id="t9", goal="find three 27 inch 4k monitors under 400", kind="web")
    rec.result_summary, rec.ok = _REPORT, False
    asyncio.run(ws._deliver(rec))


def test_the_voice_says_the_composed_line_not_the_report(world):
    said, asked = world
    _deliver()
    assert said == ["Your monitors are ready — the Dell S2725QS at $299.99 is the best pick."]
    system = asked[0][0]["content"]
    assert "Say it in English" in system and "two short spoken sentences" in system


def test_when_the_model_does_not_answer_only_the_opening_is_said(world, monkeypatch):
    said, _ = world

    class _Down:
        async def complete(self, *a, **k):
            raise TimeoutError("down")
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _Down)
    _deliver()
    assert said and len(said[0]) <= sd._MAX_CHARS and "**" not in said[0]
