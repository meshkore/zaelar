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

# THE DEFAULT VOICE OF EACH VARIANT THE PICKER SHIPS — chosen on purpose, never by list order (2026-09-25).
#
# The operator: *«la voz es diferente varias veces y me ha parecido que es random… si pido el idioma inglés de
# Estados Unidos, tiene que ser un hombre o una mujer que hable inglés perfecto de Estados Unidos. Ahora me has
# puesto una chica italiana intentando hablar inglés… Investiga y setea las voces por defecto»*. Nothing here
# was random: `default_voice` took the FIRST native voice with the right accent, and that order is the API's —
# the account list as it comes back, then the Voice Library sorted by «trending», re-fetched every week. So
# es-419 was «whoever trends this week», and a saved library voice that stopped trending was dropped and
# replaced. A default is a decision; it lives here, in a table, and the API only ever ADDS options to it.
#
# One coherent set, measured against the live library the same day: a middle-aged male voice whose use case
# is CONVERSATIONAL (an assistant talks, it does not narrate), native to the variant, and among the most
# used for it. en-US/en-GB are ElevenLabs' global premade voices (present on every account); es-ES/es-419 are
# Voice Library voices, which synthesise by id on any account (measured, see the module docstring). The
# metadata rides with the id so the pin works offline and before the first catalog fetch.
_PINNED: dict[str, dict] = {
    "en-US": {"voice": "cjVigY5qzO86Huf0OWal", "label": "Eric", "gender": "m", "lang": "en",
              "accent": "american"},           # premade · «Smooth, Trustworthy» · conversational
    "en-GB": {"voice": "JBFqnCBsd6RMkjVDRZzb", "label": "George", "gender": "m", "lang": "en",
              "accent": "british"},            # premade · «Warm, Captivating» · the premade British male
    "es-ES": {"voice": "LlZr3QuzbW4WrPjgATHG", "label": "Martin Osborne", "gender": "m", "lang": "es",
              "accent": "peninsular"},         # library · Castilian · «perfect for dialogues & casual conversation»
    "es-419": {"voice": "94zOad0g7T7K4oa7zhDq", "label": "Mauricio", "gender": "m", "lang": "es",
               "accent": "latin american"},    # library · «Neutral Spanish, conversational and calm»
}
# A bare language code (an older picker, a typed «en») means the variant we list FIRST for it.
_DEFAULT_REGION = {"en": "US", "es": "ES"}


def pinned_voice(lang: str, region: str = "") -> dict:
    """The pinned row for (lang, region), {} when that variant has no pin."""
    lang = (lang or "").strip().lower()
    region = (region or "").strip().upper() or _DEFAULT_REGION.get(lang, "")
    return dict(_PINNED.get(f"{lang}-{region}") or {})


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

    # The pinned voices of this language go FIRST and are always there — the default can never be a voice
    # the list no longer carries (a library voice that stopped trending used to be dropped and replaced).
    pinned = [dict(v, source="pinned") for v in _PINNED.values() if v.get("lang") == lang and lang]
    native_acc = pinned + [v for v in account if v.get("lang") == lang and lang]
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


# V2-734 — which ACCENTS a region means, in the vocabulary the Voice Library actually uses. Measured
# against his own cached catalog (2026-09-20): es returns `peninsular`, `latin american`, `argentine`,
# `peruvian`; en returns `american`, `british`, `australian`. The operator: *«no es lo mismo el español de
# España que el español latino»* — and before this, `es` handed him `Elena (peruvian)` because she happens
# to be first in his account, while `Sara Martin 1 (peninsular)` sat second.
#
# A region lists its accents in PREFERENCE order and nothing else: an accent nobody in the list matches
# falls through to the plain «first native» rule, which is what a language with no regional split gets.
_REGION_ACCENTS: dict[str, tuple[str, ...]] = {
    "ES":  ("peninsular", "castilian", "spanish", "european"),
    "419": ("latin american", "mexican", "colombian", "argentine", "chilean", "peruvian", "neutral"),
    "US":  ("american", "us", "north american"),
    "GB":  ("british", "english", "uk", "received pronunciation", "irish"),
}


def accents_for(region: str) -> tuple[str, ...]:
    """The accents a region prefers, best first. Empty for a region we do not split."""
    return _REGION_ACCENTS.get((region or "").strip().upper(), ())


def default_voice(lang: str, region: str = "") -> str:
    """The voice this language should speak with when the operator has not picked one.

    With a `region`, a NATIVE voice whose accent the region prefers wins — that is the entire reason
    regional variants exist in the picker (V2-734). Preference is ordered, so «peninsular» beats
    «castilian» beats nothing, and a region whose accents are all absent degrades to the plain rule rather
    than to a wrong-accent voice chosen on purpose.

    '' when we know nothing — the TTS builder then keeps the plugin's own default rather than a
    wrong-language id.
    """
    pin = pinned_voice(lang, region)
    if pin:
        return pin["voice"]
    rows = for_language(lang)
    if not rows:
        return ""
    wanted = accents_for(region)
    if wanted:
        lang = (lang or "").strip().lower()
        natives = [v for v in rows if v.get("lang") == lang and lang]
        for accent in wanted:
            hit = next((v for v in natives if (v.get("accent") or "").strip().lower() == accent), None)
            if hit:
                return hit["voice"]
    return rows[0]["voice"]


_GENDER_MARK = {"m": "\u2642", "f": "\u2640"}


def describe(v: dict) -> str:
    """How a voice reads in the ⚙ dropdown: its name, the language VARIANT it is native to, and a gender mark
    — «Eric · English (United States) ♂». A bare name («Roger», «Elena») hid that one of them was Peruvian.
    The variant's name is the picker's own (i18n/catalog.py), so it is the same words the operator chose
    his language with; an accent we cannot map shows as the accent itself."""
    name = (v.get("label") or v.get("voice") or "").strip()
    lang = (v.get("lang") or "").strip().lower()
    accent = (v.get("accent") or "").strip().lower()
    where = ""
    if lang:
        region = next((r for r, accs in _REGION_ACCENTS.items() if accent in accs), "")
        if region:
            where = _variant_name(f"{lang}-{region}") or f"{lang} ({accent})"
        else:   # an accent the picker has no variant for (Australian, Indian…) still says which one it is
            base = _variant_name(lang) or lang
            where = f"{base} ({accent})" if accent else base
    mark = _GENDER_MARK.get((v.get("gender") or "").strip().lower(), "")
    return " ".join(x for x in (name, "·" if where else "", where, mark) if x)


def _variant_name(code: str) -> str:
    try:
        from i18n import catalog
        for row in catalog.picker():
            if str(row.get("code") or "").lower() == code.lower():
                return str(row.get("native") or row.get("name") or "")
        base = code.split("-")[0].lower()
        for row in catalog.picker():
            if str(row.get("base") or row.get("code") or "").lower() == base and "-" not in code:
                return str(row.get("native") or row.get("name") or "").split(" (")[0]
    except Exception:  # noqa: BLE001 — a label is never worth an exception
        pass
    return ""


__all__ = ["for_language", "default_voice", "accents_for", "refresh", "pinned_voice", "describe"]
