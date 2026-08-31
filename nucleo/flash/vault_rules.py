"""nucleo/flash/vault_rules.py — VOICE commands that change the vault's security CONFIGURATION (V2-060 F2).

They are **HARD user rules**: they do not guide via prompts (those are the style rules, V2-046), but are applied
DETERMINISTICALLY in code and only change through an EXPLICIT command (or from ⚙). Regex detection is es/en (the
FlashBrain remains non-reasoning). It currently covers one case: **does zaelar read secrets aloud?** (“don't tell me
secrets by voice” → screen only; “can you tell them to me by voice” → comfortable mode). It is persisted in
`state.security` (2nd class).

It is checked VERY early in the turn (before the gate/routing) — like `attention.hard_interrupt` — so that a
configuration command is never buried. It returns a confirmation PHRASE to speak (localized), or None.
"""
from __future__ import annotations

import re
import unicodedata


def _n(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_SECRET_WORD = r"(?:secretos?|secrets?|contrase[nñ]as?|claves?|datos? (?:privados?|protegidos?)|passwords?)"
_BY_VOICE = r"(?:en voz alta|por voz|hablando|en alto|out loud|aloud|by voice)"
_NEG = r"(?:no|nunca|don'?t|do not|never)"

# Do NOT read secrets aloud → screen only
_NO_VOICE_RE = re.compile(
    rf"\b{_NEG}\b[^.]*\b(?:digas|leas|menciones|reproduzcas|say|read|tell)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b{_SECRET_WORD}\b[^.]*\bsolo (?:en|por) pantalla\b"
    rf"|\bmodo (?:de )?maxima seguridad\b",
)
# DO read secrets aloud → comfortable mode
_YES_VOICE_RE = re.compile(
    rf"\b(?:si|puedes|vale|ok)\b[^.]*\b(?:decir|leer|say|read)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b(?:dime|leeme|read me|read)\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\bmodo (?:de )?comod\w*\b[^.]*{_SECRET_WORD}",
)


def detect(text: str) -> tuple[str, object] | None:
    """→ ('secrets_voice', bool) if the turn is a vault configuration command; None otherwise."""
    t = _n(text)
    if not t:
        return None
    # NO takes precedence over YES (more specific and safer)
    if _NO_VOICE_RE.search(t):
        return ("secrets_voice", False)
    if _YES_VOICE_RE.search(t):
        return ("secrets_voice", True)
    return None


def apply(cmd: tuple[str, object]) -> str:
    """Applies the security rule (persists it in state.security) and returns the localized confirmation phrase."""
    key, value = cmd
    try:
        from memory import state as _state
        _state.set_security_flag(key, value)
    except Exception:
        pass
    try:
        from voice.engine.core import langs as _lg
        L = _lg.current_language()
        es = L.code == "es"
    except Exception:
        es = True
    if key == "secrets_voice":
        if value:
            return "Vale, te leeré los secretos en voz alta cuando me los pidas." if es \
                else "Alright, I'll read secrets aloud when you ask."
        return "Hecho: no diré tus secretos en voz alta, solo te los mostraré en pantalla." if es \
            else "Done: I won't say your secrets aloud, I'll only show them on screen."
    return "Hecho." if es else "Done."
