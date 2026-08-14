"""
i18n.init.detect — first-run language auto-detection (V2-089 P3).

"We're an AI; we should figure it out." On a brand-new install (the operator hasn't picked a language yet) we
detect the language from their FIRST utterances and lock it — no trip to settings. INITIALIZATION, not the hot
path: it runs a couple of times at the very start, then never again.

Gate: should_detect() is True only until a language is explicitly set (persisted `stt_language` in settings.json
— written either by this lock() or by a manual ⚙ change). So auto-detection NEVER overrides a deliberate choice.

Detection: a Unicode-script heuristic catches non-Latin languages instantly (Arabic, CJK, Cyrillic, …); anything
Latin-script (es/en/fr/…) goes to a cheap constrained LLM classify. Works off whatever the first-run STT (running
in auto mode) transcribed.

Lock: persist ZAELAR_LANGUAGE, prepare() the UI bundle (generate if the language is new), and emit an SSE
`language` event so the frontend flips the whole UI live.
"""
from __future__ import annotations

import json
import re

from loguru import logger

# Unicode-script → ISO-639-1. Order matters: check kana (ja) before bare Han (zh).
_SCRIPT = [
    ("ja", r"[぀-ヿ]"),                 # hiragana/katakana
    ("ko", r"[가-힯]"),                 # hangul
    ("zh", r"[一-鿿]"),                 # han (after kana → zh)
    ("ar", r"[؀-ۿ]"),                 # arabic
    ("he", r"[֐-׿]"),                 # hebrew
    ("ru", r"[Ѐ-ӿ]"),                 # cyrillic
    ("el", r"[Ͱ-Ͽ]"),                 # greek
    ("hi", r"[ऀ-ॿ]"),                 # devanagari
    ("th", r"[฀-๿]"),                 # thai
]

_should_cache: bool | None = None


def should_detect() -> bool:
    """True on a fresh install where no language has been chosen yet. Cached (invalidated on lock)."""
    global _should_cache
    if _should_cache is not None:
        return _should_cache
    persisted = {}
    try:
        from config.settings import SETTINGS_FILE
        persisted = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        persisted = {}
    _should_cache = not str(persisted.get("stt_language") or "").strip()
    return _should_cache


def _by_script(text: str) -> str | None:
    for code, pat in _SCRIPT:
        if re.search(pat, text):
            return code
    return None


def _by_llm(text: str) -> str | None:
    """Constrained classify: return the ISO-639-1 code of the text, nothing else. Fail-open → None."""
    try:
        from nucleo import memllm
        raw = memllm.chat_sync(
            "i18n",
            "Identify the language of the user's text. Reply with ONLY its ISO 639-1 two-letter code "
            "(lowercase, e.g. 'en', 'es', 'fr', 'de', 'pt'). No other text.",
            text[:500], max_tokens=4, temperature=0.0, timeout=20.0)
        m = re.search(r"[a-z]{2}", (raw or "").strip().lower())
        return m.group(0) if m else None
    except Exception:
        return None


def classify(text: str) -> str | None:
    """Best-effort language code for a transcript. Script heuristic first (instant, non-Latin), else LLM."""
    text = (text or "").strip()
    if len(text) < 2:
        return None
    return _by_script(text) or _by_llm(text)


async def lock(code: str) -> dict:
    """Commit the detected language: persist it, prepare its UI bundle, and tell the frontend to switch. Idempotent
    enough — once persisted, should_detect() goes False so this won't fire again."""
    global _should_cache
    code = (code or "").strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}", code):
        return {"ok": False, "code": code}
    logger.info(f"i18n.detect: locking operator language → '{code}'")
    try:
        from config import settings as _s
        _s.update({"stt_language": code})          # persist + env (voice realigns on next reconnect)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: settings.update failed: {e}")
    _should_cache = False                           # stop detecting
    # THE MEMORY'S CANONICAL LANGUAGE. Locking used to move the voice, the STT and the UI and leave the memory
    # behind: `state.language` is what `mem_processor._render` reads to decide the language every pill is written
    # in, and nothing here ever wrote it. So a French operator got French speech, French STT and a French UI —
    # while their memory was distilled, forever, into whatever the default happened to be. The memory is
    # deliberately MONOLINGUAL in the operator's language (2026-07-10); that only holds if detection moves it too.
    try:
        from memory import api as _memory
        _memory.set_state({"language": code})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: could not set the memory's canonical language: {e}")
    try:
        from i18n import init as _init
        await _init.prepare(code)                   # generate/upgrade the UI bundle (preset → instant)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: prepare('{code}') failed: {e}")
    try:
        from voice.observer import emit
        emit("language", "changed", role="system", extra={"code": code})   # → frontend applyLang(code)
    except Exception:
        pass
    return {"ok": True, "code": code}
