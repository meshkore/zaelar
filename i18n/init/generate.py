"""
i18n.init.generate — LLM translation of UI strings into a new language (V2-089).

INITIALIZATION only (never the hot path). Given a batch of {key: english}, translate to the target language and
return {key: translated}, preserving {placeholders}, punctuation, emoji, and technical tokens. Off-hot-path, so
quality wins over latency: a strong model (config §memory.i18n_model, default deepseek-v4-pro on the DIRECT
broker) through the shared off-path caller (nucleo.memllm). Runs inside asyncio.to_thread so it doesn't block
the event loop. Why that model — and why NOT the memory's own deepseek — is argued in `nucleo/memllm.py`
(`_DEFAULTS["i18n"]`): measured at the real batch size, not guessed.

Fail-open: if the model is unavailable, returns what it could (possibly empty) — the frontend falls back to
English, so a missing translation degrades gracefully instead of breaking the UI.
"""
from __future__ import annotations

import asyncio
import json

from loguru import logger

# Common ISO-639-1 → English name, so the prompt can name the target language. Fallback: the code itself
# (the model still handles it — "the language with code 'xx'").
_LANG_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese",
    "zh": "Chinese (Simplified)", "ja": "Japanese", "ko": "Korean", "ru": "Russian", "ar": "Arabic",
    "hi": "Hindi", "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "el": "Greek", "he": "Hebrew", "th": "Thai", "vi": "Vietnamese",
    "id": "Indonesian", "cs": "Czech", "ro": "Romanian", "hu": "Hungarian", "uk": "Ukrainian", "ca": "Catalan",
}

_BATCH = 50   # keys per LLM call — small enough to stay well within context + keep JSON reliable


def language_name(code: str) -> str:
    return _LANG_NAMES.get((code or "").strip().lower(), (code or "").strip())


def _system(code: str) -> str:
    name = language_name(code)
    return (
        f"You are a professional software UI localizer. Translate short product-UI strings from English into "
        f"{name}. You will receive a JSON object mapping opaque KEYS to English text. Return ONLY a JSON object "
        f"with the SAME keys, each mapped to the {name} translation — no prose, no code fences.\n"
        "RULES: (1) Keep every {placeholder} token EXACTLY as-is (same name, same braces) — they are interpolated "
        "at runtime. (2) Preserve punctuation, the middot ' · ', ellipses, emoji and leading/trailing spacing. "
        "(3) Do NOT translate technical/brand tokens: API, STT, TTS, LLM, URL, IMAP, SMTP, OAuth, QR, WhatsApp, "
        "Telegram, Spotify, YouTube, MeshKore, zaelar, Fly, LiveKit, Kokoro, and product names. "
        # The PROPER NAMES of system components (operator rule, 2026-08-12): FlashBrain and Brain Workers
        # are written the SAME in Spanish, English, or Chinese. Translating them (“fast brain,” “code agents”) breaks
        # conversations with the operator and the documentation, which names them this way in every language.
        "The NAMES OF OUR OWN COMPONENTS are proper nouns and must appear VERBATIM, never translated nor "
        "transliterated: FlashBrain, Brain Workers, Susurro, MeshKore, Colmena, Energy. (4) Natural, "
        "concise, native phrasing for a UI (buttons/labels/tooltips) — match the register, not word-for-word. "
        "(5) Keep ALL-CAPS emphasis where the English uses it for a warning."
    )


def _parse(raw: str) -> dict:
    if not raw:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
        return {k: v for k, v in d.items() if isinstance(v, str)} if isinstance(d, dict) else {}
    except Exception:
        return {}


def _translate_batch_sync(code: str, batch: dict[str, str]) -> dict[str, str]:
    from nucleo import memllm
    raw = memllm.chat_sync("i18n", _system(code), json.dumps(batch, ensure_ascii=False),
                           max_tokens=4000, temperature=0.2, timeout=90.0)
    out = _parse(raw or "")
    return {k: out[k] for k in batch if k in out and isinstance(out[k], str) and out[k].strip()}


async def translate(code: str, missing: dict[str, str]) -> dict[str, str]:
    """Translate {key: english} → {key: target}. Batched; fail-open per batch."""
    keys = list(missing.keys())
    result: dict[str, str] = {}
    for start in range(0, len(keys), _BATCH):
        chunk = {k: missing[k] for k in keys[start:start + _BATCH]}
        try:
            got = await asyncio.to_thread(_translate_batch_sync, code, chunk)
            result.update(got)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"i18n.generate[{code}]: batch {start//_BATCH} failed: {str(e)[:160]}")
    return result
