"""nucleo/flash/vault_rules.py — comandos de VOZ que cambian la CONFIGURACIÓN de seguridad de la bóveda (V2-060 F2).

Son **user rules DURAS**: no guían por prompt (eso son las de estilo, V2-046), sino que se aplican DETERMINISTA en
código y solo cambian por una orden EXPLÍCITA (o desde el ⚙). Detección regex es/en (el FlashBrain sigue
no-razonador). Hoy cubre una: **¿zaelar lee los secretos en voz alta?** («no me digas los secretos por voz» →
solo pantalla; «puedes decírmelos por voz» → modo cómodo). Se persiste en `state.security` (2ª clase).

Se comprueba MUY pronto en el turno (antes del gate/routing) — como `attention.hard_interrupt` — para que una
orden de configuración nunca quede enterrada. Devuelve una FRASE de confirmación a hablar (localizada), o None.
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

# NO leer secretos por voz → solo pantalla
_NO_VOICE_RE = re.compile(
    rf"\b{_NEG}\b[^.]*\b(?:digas|leas|menciones|reproduzcas|say|read|tell)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b{_SECRET_WORD}\b[^.]*\bsolo (?:en|por) pantalla\b"
    rf"|\bmodo (?:de )?maxima seguridad\b",
)
# SÍ leer secretos por voz → modo cómodo
_YES_VOICE_RE = re.compile(
    rf"\b(?:si|puedes|vale|ok)\b[^.]*\b(?:decir|leer|say|read)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b(?:dime|leeme|read me|read)\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\bmodo (?:de )?comod\w*\b[^.]*{_SECRET_WORD}",
)


def detect(text: str) -> tuple[str, object] | None:
    """→ ('secrets_voice', bool) si el turno es una orden de config de bóveda; None si no lo es."""
    t = _n(text)
    if not t:
        return None
    # el NO manda sobre el SÍ (más específico y más seguro)
    if _NO_VOICE_RE.search(t):
        return ("secrets_voice", False)
    if _YES_VOICE_RE.search(t):
        return ("secrets_voice", True)
    return None


def apply(cmd: tuple[str, object]) -> str:
    """Aplica la regla de seguridad (persiste en state.security) y devuelve la frase de confirmación localizada."""
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
