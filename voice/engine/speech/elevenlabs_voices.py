"""ElevenLabs voice catalog — WHICH voice is right for the language we are speaking (V2-672).

The operator, after a factory reset (2026-09-11): *«la voz que viene por defecto en español habla bien
español, pero habla mal inglés. Probablemente hay que poner una voz que esté preparada para el inglés, y si
hay alguien que habla chino o alemán o suahili tenemos que ponerle una voz que esté entrenada para esos
idiomas»* — plus, in the settings, the operator should be able to pick their own.

He was describing a real, shipped default. `voice/engine/core/config.py` hardcoded
`elevenlabs_voice_id = "KHCvMklQZZo0O30ERnVn"` — a Castilian professional voice — for EVERY language,
because V2-035 chose it when the product spoke one. The TTS model is multilingual, so an English turn does
not fail; it comes out with a Spanish accent, which is exactly what he heard.

MEASURED against the live API before any of this was written (2026-09-11, the operator's own key):

  · `GET /v1/voices` returns the ACCOUNT's voices — 23, of which 21 are ElevenLabs `premade` and **every
    single premade one is `labels.language: en`**. So the premade set cannot answer "a voice trained for
    German": it does not contain one, and picking from it by `verified_languages` would only pick an
    English voice that has been checked once in German.
  · `GET /v1/shared-voices?language=<code>` returns the Voice Library filtered to voices NATIVE to that
    language — real ones, with accents (es → latin american, peruvian; zh → beijing/taiwan mandarin) — and
    `sw` honestly returns ZERO, which is the answer for a language with no native voice.
  · A shared-library `voice_id` WORKS DIRECTLY in `POST /v1/text-to-speech/{id}` with no "add to my voices"
    step (verified with a nine-character synthesis, 200 + real audio). Without that measurement this whole
    module would have shipped a picker full of ids that 400.
  · The key must come from the CREDENTIAL STORE, not the environment: the `.env` copy on this machine is
    stale and answers 401 while the store's key answers 200. `server/common.py` loads the store with
    `override=True`, so the env is usually right — but "usually" is how a voice picker ends up empty for
    reasons nobody can see, so this module asks the store first and says so.

NETWORK DISCIPLINE. Nothing here may run on a voice turn. `for_language()` reads the on-disk cache only;
the fetch happens at ONBOARDING (a language is locked) and on an explicit refresh from the ⚙. A cold cache
with a key present is allowed ONE attempt per process, so the first ⚙ open fills it and a dead network does
not retry on every call. Every failure degrades to the shipped table, never to an exception: a voice picker
that raises takes the settings panel down with it.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# The ACCOUNT's premade voices as measured on 2026-09-11 — the offline floor, and honest about what it is:
# all English-native, so it is the right answer for `en` and a multilingual fallback for anything else.
# It exists so that an install with no network, or a key without `voices_read`, still offers a real choice
# instead of a single env var. These ids are ElevenLabs' global premade voices, not account-specific.
_SHIPPED: tuple[dict, ...] = (
    {"voice": "nPczCjzI2devNBz1zQrb", "label": "Brian", "gender": "m", "lang": "en", "accent": "american"},
    {"voice": "EXAVITQu4vr4xnSDxMaL", "label": "Sarah", "gender": "f", "lang": "en", "accent": "american"},
    {"voice": "JBFqnCBsd6RMkjVDRZzb", "label": "George", "gender": "m", "lang": "en", "accent": "british"},
    {"voice": "Xb7hH8MSUJpSbSDYk0k2", "label": "Alice", "gender": "f", "lang": "en", "accent": "british"},
    {"voice": "cjVigY5qzO86Huf0OWal", "label": "Eric", "gender": "m", "lang": "en", "accent": "american"},
    {"voice": "XrExE9yKIg1WjnnlVkGX", "label": "Matilda", "gender": "f", "lang": "en", "accent": "american"},
)

_API = "https://api.elevenlabs.io/v1"
_TTL_S = 7 * 24 * 3600          # the Voice Library moves in weeks, not minutes
_LIBRARY_PER_LANG = 12          # enough to choose from; a picker nobody scrolls is not a better picker
_TIMEOUT_S = 12.0

_tried_cold: set[str] = set()   # one network attempt per (process, language) on a cold cache


def _cache_path() -> Path:
    from ..core.env import ZAELAR_ROOT
    return Path(os.getenv("ZAELAR_WORKSPACE") or ZAELAR_ROOT) / "config" / "elevenlabs_voices.json"


def _api_key() -> str:
    """The live key. The credential store WINS over the environment — see the module docstring: the two can
    disagree, and when they do the env is the stale one."""
    try:
        from config import credentials
        got = (credentials.get("ELEVENLABS_API_KEY") or "").strip()
        if got:
            return got
    except Exception:
        pass
    return (os.getenv("ELEVENLABS_API_KEY") or "").strip()


def _read_cache() -> dict:
    try:
        d = json.loads(_cache_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_cache(d: dict) -> None:
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass                     # a cache that cannot be written costs a fetch, never a failure


def _fresh(entry: dict) -> bool:
    return bool(entry) and (time.time() - float(entry.get("at") or 0)) < _TTL_S


def _norm_account(v: dict) -> dict:
    labels = v.get("labels") or {}
    return {"voice": v.get("voice_id") or "", "label": (v.get("name") or "").split(" - ")[0].strip(),
            "gender": {"male": "m", "female": "f"}.get((labels.get("gender") or "").lower(), "n"),
            "lang": (labels.get("language") or "").lower(), "accent": labels.get("accent") or "",
            "source": "account"}


def _norm_library(v: dict) -> dict:
    return {"voice": v.get("voice_id") or "", "label": (v.get("name") or "").split(" - ")[0].strip(),
            "gender": {"male": "m", "female": "f"}.get((v.get("gender") or "").lower(), "n"),
            "lang": (v.get("language") or "").lower(), "accent": v.get("accent") or "",
            "source": "library"}


def _fetch(lang: str) -> dict:
    """One round-trip per surface: the account's own voices, and the Voice Library for THIS language.

    Returns `{"at": ts, "account": [...], "library": [...]}`. Raises nothing — a partial result is still
    useful (the account half alone already beats a single hardcoded id)."""
    key = _api_key()
    out: dict = {"at": time.time(), "account": [], "library": []}
    if not key:
        return out
    try:
        import httpx
    except Exception:
        return out
    headers = {"xi-api-key": key}
    try:
        with httpx.Client(timeout=_TIMEOUT_S) as client:
            try:
                r = client.get(f"{_API}/voices", headers=headers)
                if r.status_code == 200:
                    out["account"] = [_norm_account(v) for v in (r.json().get("voices") or [])]
            except Exception:
                pass
            if lang:
                try:
                    r = client.get(f"{_API}/shared-voices", headers=headers,
                                   params={"language": lang, "page_size": _LIBRARY_PER_LANG,
                                           "sort": "trending"})
                    if r.status_code == 200:
                        out["library"] = [_norm_library(v) for v in (r.json().get("voices") or [])]
                except Exception:
                    pass
    except Exception:
        pass
    out["account"] = [v for v in out["account"] if v.get("voice")]
    out["library"] = [v for v in out["library"] if v.get("voice")]
    return out


def refresh(lang: str) -> dict:
    """Fetch and cache this language's catalog. The ONLY function here that touches the network on purpose —
    called at onboarding and from the ⚙, never from a turn."""
    lang = (lang or "").strip().lower()
    got = _fetch(lang)
    cache = _read_cache()
    cache[lang or "_"] = got
    _write_cache(cache)
    return got


def for_language(lang: str) -> list[dict]:
    """The voices to offer for `lang`, best first — and "best" is defined, not felt:

      1. a voice NATIVE to the language (the account's own first, then the Voice Library's), because that is
         what the operator asked for and the only thing that fixes an accent;
      2. anything else the account has, as the multilingual fallback — kept, and kept LAST, because a
         language with no native voice (measured: Swahili) must still be able to speak.

    Cache-only unless the cache is cold, in which case ONE fetch per process per language.
    """
    lang = (lang or "").strip().lower()
    entry = _read_cache().get(lang or "_") or {}
    if not _fresh(entry) and lang not in _tried_cold and _api_key():
        _tried_cold.add(lang)
        entry = refresh(lang)
    account = list(entry.get("account") or [])
    library = list(entry.get("library") or [])
    if not account and not library:
        account = [dict(v, source="shipped") for v in _SHIPPED]

    native_acc = [v for v in account if v.get("lang") == lang and lang]
    native_lib = [v for v in library if v.get("lang") == lang and lang]
    other = [v for v in account if v not in native_acc]
    # English-native first among the fallbacks: the multilingual models were trained with English as the
    # anchor, so an English voice reading French is the least bad of the bad options.
    other.sort(key=lambda v: (v.get("lang") != "en", v.get("label") or ""))

    seen, out = set(), []
    for v in native_acc + native_lib + other:
        vid = v.get("voice")
        if vid and vid not in seen:
            seen.add(vid)
            out.append({**v, "native": v.get("lang") == lang and bool(lang)})
    return out


def default_voice(lang: str) -> str:
    """The voice this language should speak with when the operator has not picked one. '' when we know
    nothing — the TTS builder then keeps the plugin's own default rather than a wrong-language id."""
    rows = for_language(lang)
    return rows[0]["voice"] if rows else ""


__all__ = ["for_language", "default_voice", "refresh"]
