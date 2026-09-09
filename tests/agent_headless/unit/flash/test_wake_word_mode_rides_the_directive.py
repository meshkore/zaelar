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

The mode's product name is «Modo Wake Word» (operator decision 2026-09-09); «wakeworld» is the STT's own
garble of it, transcribed verbatim in session 8a07e8d9.
"""
from __future__ import annotations

import re

from nucleo.flash import identity_actions


# ── 1 · the detector reads the model's real paraphrases ─────────────────────────────────────────────────────

def test_the_measured_respond_paraphrase_activates_the_mode():
    d = ("Solo responder cuando el operador diga el nombre del asistente (Johnny); "
         "el resto del tiempo permanecer en silencio")
    assert identity_actions.resolve(d) == ("attention", "smart")


def test_the_mode_is_addressable_by_its_product_name_and_its_stt_garble():
    for d in ("activa el modo wake word", "Activa el modo wakeworld",
              "activar el modo de activación por palabra clave"):
        assert identity_actions.resolve(d) == ("attention", "smart"), d


def test_deactivation_by_name_and_by_phrase():
    for d in ("desactiva el modo wake word", "quita el wake word", "vuelve a escucharme siempre",
              "responde siempre, aunque no diga tu nombre"):
        assert identity_actions.resolve(d) == ("attention", "always"), d


def test_an_unrelated_directive_stays_a_plain_style_rule():
    for d in ("Sé más directo en las respuestas", "En Gmail muestra solo el asunto de los mensajes"):
        assert identity_actions.resolve(d) is None, d


def test_a_rename_still_wins_over_the_attention_classes():
    assert identity_actions.resolve("El asistente debe llamarse Johnny") == ("rename", "Johnny")


# ── 2 · the prompt HOLDS the fact: mode name, wake word = assistant name, tool, current state ───────────────

def _live_state_with(monkeypatch, mode: str, name: str) -> str:
    import config.settings as settings
    from memory import api as memapi
    real_get = settings.get
    monkeypatch.setattr(settings, "get",
                        lambda k, d=None: mode if k == "attention_mode" else real_get(k, d))
    monkeypatch.setattr(memapi, "state", lambda: {"assistant_name": name, "location": "Soria"})
    from nucleo.flash import prompt
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


# ── 3 · wiring guard: BOTH channels ride identity_actions (V2-108's parallel-impl trap) ─────────────────────

def _stripped_source(path: str) -> str:
    src = open(path, encoding="utf-8").read()
    return re.sub(r"(?m)#.*$", "", src)


def test_both_channels_call_identity_actions():
    # V2-633 moved the whole set_style_directive path into nucleo/flash/style_directive.py — the guard
    # follows the CHANNEL (V2-555): each channel's entry must delegate there, and the shared module must
    # still ride identity_actions on both faces.
    voice = _stripped_source("voice/engine/llm/providers/nucleo.py")
    probe = _stripped_source("nucleo/flash/probe.py")
    shared = _stripped_source("nucleo/flash/style_directive.py")
    assert "style_directive" in voice and ".handle(" in voice
    assert "style_directive" in probe and ".handle_probe(" in probe
    assert "identity_actions" in shared and ".handle_voice(" in shared and ".handle_probe(" in shared


def test_the_probe_mute_ladder_acks_the_identity_actions():
    """Measured live 2026-09-09: «Activa el modo wake word» APPLIED the mode and the generic mute backstop
    answered «Perdona, se me ha ido» — a fault-owning ack over a done action. The probe's per-action mute
    ladder must ack the identity labels like it acks "style" (the voice channel already does, via
    style_fired → data_ack)."""
    probe = _stripped_source("nucleo/flash/probe.py")
    assert re.search(r'action in \("style", "attention_mode", "rename_assistant"\)', probe)
