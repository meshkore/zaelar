"""A corrected call writes its text in the SESSION's language, named — never the refusal's (demo pass 102, 2026-10-04).

E3 «send the invoice to andrew, tell him we're already trying inworld…» in an English session: `forward` was
refused for a missing `text` with a Spanish reason, and the one-pass repair wrote the note to Andrew as «Ya
estamos probando Inworld, resérvalo.» — the prompt only said «the operator's language», and the refusal and the
manifest it read were both Spanish. The repair now names the language.
"""
from __future__ import annotations

import asyncio


def _system_prompt(monkeypatch, lang: str) -> str:
    from nucleo.flash import act_repair, fast_client
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(lang))
    seen = []

    class _FC:
        async def complete(self, messages, **_kw):
            seen.append(messages[0]["content"])
    monkeypatch.setattr(fast_client, "FastClient", _FC)
    asyncio.run(act_repair.call_for_refusal("send the invoice to andrew, tell him we're already trying inworld",
                                            "mensajeria", "forward", {"contact": "Andrew"},
                                            "falta `text` en forward: la nota para esa persona"))
    assert seen, "the repair pass never ran"
    return seen[0]


def test_an_english_session_is_told_english(monkeypatch):
    assert "in English" in _system_prompt(monkeypatch, "en")


def test_a_spanish_session_is_told_spanish(monkeypatch):
    p = _system_prompt(monkeypatch, "es")
    assert "in Spanish" in p and "in English" not in p
