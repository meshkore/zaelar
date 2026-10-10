"""nucleo/flash/outgoing_lang.py — what LEAVES goes in the session's language (demo pass 106, 2026-10-04).

E3 «send the invoice to quinn, tell him we're already trying inworld…» in an English session, three passes
running: the note said «Ya estamos probando Inworld, así que adelante con la reserva.» The model reads every
tool description in Spanish and copies it into the text it writes for someone else; the language lock in the
prompt (2.230) did not hold it. So the mechanism sits at the door: before an `external.send` act runs, a text
field written in the OTHER of the two product languages is translated once. Only es↔en is told apart — the two
languages the product's descriptions and its sessions use — and too few words to tell is left alone. Never
raises: an unreadable text, or a translation that fails, sends what the model wrote.
"""
from __future__ import annotations

import re

_TEXT_KEYS = ("text", "note", "body", "message")
_MARKERS = {
    "es": {"el", "la", "los", "las", "que", "de", "del", "y", "con", "para", "por", "ya", "estamos", "así", "una",
           "un", "es", "está", "nos", "vemos", "hola", "oye", "mañana", "hora", "adelante", "reserva", "gracias",
           # V2-781: what a widget's refusal is made of («No encuentro ese vídeo en la lista» had one marker)
           "ese", "esa", "hay", "más", "nada", "encuentro", "dime", "qué", "cuál", "vídeo", "vídeos", "lista",
           "vacía", "puedo", "tengo"},
    "en": {"the", "and", "we", "we're", "already", "to", "of", "is", "are", "it", "you", "with", "for", "see",
           "tomorrow", "hey", "hi", "thanks", "please", "go", "ahead", "book", "our", "your", "at"},
}
_MIN_MARKERS = 2


def language_of(text: str) -> str:
    """"es", "en", or "" when the text does not say."""
    words = re.findall(r"[a-záéíóúñü']+", str(text or "").lower())
    es = sum(w in _MARKERS["es"] for w in words)
    en = sum(w in _MARKERS["en"] for w in words)
    if max(es, en) < _MIN_MARKERS or es == en:
        return ""
    return "es" if es > en else "en"


#: Off inside the suite (tests/conftest.py), like `spoken_delivery.LIVE`: a reply door must not reach the network.
LIVE = True


async def _translate(text: str, lang_name: str) -> str:
    if not LIVE:
        return ""
    from nucleo.flash.fast_client import FastClient
    out = await FastClient().complete(
        [{"role": "system", "content": f"Translate the message into {lang_name}. Keep names, numbers, times and the "
                                       f"tone. Answer with the translated message only."},
         {"role": "user", "content": text}],
        max_tokens=300, no_thinking=True)
    return str(out or "").strip().strip("«»\"")


async def in_session_language(widget_id: str, action: str, payload: dict) -> dict:
    """`payload`, with any outgoing text in the other product language translated to the session's."""
    try:
        from widgets import effects as _fx
        if not isinstance(payload, dict) or not _fx.carries(widget_id, action, _fx.EXTERNAL_SEND):
            return payload
        from i18n import langs as _lg
        code = str(_lg.current_code() or "").lower()[:2]
        if code not in _MARKERS:
            return payload
        out = dict(payload)
        for k in _TEXT_KEYS:
            v = out.get(k)
            if isinstance(v, str) and language_of(v) not in ("", code):
                t = await _translate(v, _lg.spec(code).name)
                if t and language_of(t) != language_of(v):
                    out[k] = t
                    _note(widget_id, action, v, t)
        return out
    except Exception as e:  # noqa: BLE001
        _note(widget_id, action, "", f"translation skipped: {type(e).__name__}")
        return payload


def foreign_to_session(text: str) -> bool:
    """True when `text` reads as the OTHER product language — the synchronous check, so a caller whose await points
    matter (the proactive delivery queue) only yields when there is something to translate."""
    try:
        from i18n import langs as _lg
        code = str(_lg.current_code() or "").lower()[:2]
        return code in _MARKERS and language_of(text) not in ("", code)
    except Exception:  # noqa: BLE001
        return False


async def said_in_session_language(text: str) -> str:
    """`text` (a reply or a spoken notice) in the session's language — «I'm in Madrid» turned an English session
    Spanish (V2-781). Same rule as the outgoing door: only es↔en, too few words to tell is left alone."""
    try:
        from i18n import langs as _lg
        code = str(_lg.current_code() or "").lower()[:2]
        if code in _MARKERS and language_of(text) not in ("", code):
            t = await _translate(text, _lg.spec(code).name)
            if t and language_of(t) != language_of(text):
                _note("reply", "say", text, t)
                return t
    except Exception as e:  # noqa: BLE001
        _note("reply", "say", "", f"translation skipped: {type(e).__name__}")
    return text


def _note(widget_id: str, action: str, before: str, after: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🌐 texto que sale, en el idioma de la sesión", role="system", text=f"{before[:80]} → {after[:80]}",
             extra={"cat": "flash", "id": widget_id, "action": action})
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"outgoing_lang note: {e}")
