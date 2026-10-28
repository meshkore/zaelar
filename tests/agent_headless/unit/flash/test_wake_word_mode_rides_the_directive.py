"""Wake Word Mode: the toggle rides `set_style_directive`, and the prompt teaches that the mode exists.

Measured live (sessions 76bd0bb5 and 8a07e8d9, 2026-09-09), the two failures this file pins:

1. Asked «activa ese modo», the model DID call `set_style_directive` — with the paraphrase «Solo responder
   cuando el operador diga el nombre del asistente (Johnny); el resto del tiempo permanecer en silencio».
   The detector's listen-only word classes («escuchar»/«listen») missed «responder», so the directive fell
   through to the free-text-rule branch: a stale rule in `state.rules` and a mode that never changed by voice.

2. Asked to activate it in the next session, the model — with the assistant name AND the operator's name in
   its state block — answered «¿con qué palabra quieres que me active y cuál es tu nombre (que ahora mismo no
   lo tengo)?». Nothing in the prompt said the mode EXISTS, that the wake word IS the assistant's name, or
   which tool toggles it. `live_state()` carries that line now.

Since refactor2710-07 WHETHER a directive toggles the mode is the brief's `identity_change` verdict
(`nucleo/turn/identity`, tested in `test_the_name_it_answers_to_is_the_name_it_says`), never word classes over the
paraphrase. The mode's product name is «Modo Wake Word» (operator decision 2026-09-09); «wakeworld» is the STT's own
garble of it, transcribed verbatim in session 8a07e8d9.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import re




# ── 2 · the prompt HOLDS the fact: mode name, wake word = assistant name, tool, current state ───────────────

def _live_state_with(monkeypatch, mode: str, name: str) -> str:
    import config.settings as settings
    from memory import api as memapi
    real_get = settings.get
    monkeypatch.setattr(settings, "get",
                        lambda k, d=None: mode if k == "attention_mode" else real_get(k, d))
    monkeypatch.setattr(memapi, "state", lambda: {"assistant_name": name, "location": "Soria"})
    from nucleo.turn.prompt import live_state as prompt
    return prompt.live_state()


def test_the_prompt_names_the_mode_the_wake_word_and_the_tool(monkeypatch):
    block = _live_state_with(monkeypatch, "smart", "Johnny")
    assert "MODO WAKE WORD" in block
    assert "«Johnny»" in block                      # the wake word IS the current name, never a literal "zaelar"
    assert "set_style_directive" in block           # the toggle's door is named, so the model calls instead of asking
    assert "ACTIVADO" in block


def test_the_prompt_says_when_the_mode_is_off(monkeypatch):
    block = _live_state_with(monkeypatch, "always", "Zaelar")
    assert "MODO WAKE WORD" in block and "desactivado" in block and "ACTIVADO" not in block



def _stripped_source(path: str) -> str:
    src = _vts.read(path)
    return re.sub(r"(?m)#.*$", "", src)


