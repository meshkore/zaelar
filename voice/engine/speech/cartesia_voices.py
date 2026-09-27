"""Cartesia voice catalog — which voice speaks each language variant (V2-775).

Same contract as `inworld_voices.py` / `elevenlabs_voices.py`, for the same reason those exist.

WHAT WENT WRONG (operator, 2026-09-27): a local demo started in US English and *«parecía un español hablando
en inglés»*. Inworld had run out of credits, the TTS had been switched to Cartesia, and Cartesia had ONE default
voice for every language: `CARTESIA_VOICE_ID` = Marcos, a Castilian voice, and the builder never looked at the
language. `voices.py` treated Cartesia as multilingual ("one voice speaks any language") — true in the sense
that the synthesis does not fail, false in the sense that matters: the accent is the voice's, not the
language's. The same defect V2-672 fixed for ElevenLabs, one provider over.

HOW THE PINS WERE CHOSEN — from Cartesia's own metadata, not by name (2026-09-27). `GET /voices?language=<l>`
returns, per voice, `country` and `accents[]` with `is_native`. Each pin is an adult male voice whose use case
is an assistant/conversation and whose NATIVE locale is the variant:

  es-ES  Marcos    native es-ES · «Calm, measured Spanish male»  (the old universal default, now Spain only)
  es-419 Mateo     native es-MX · «Warm, genuine Mexican male perfect for conversational platforms»
  en-US  Daniel    native en-US (general-american) · «male voice for digital assistants»
  en-GB  George    native en-GB · «Steady, British male voice for capable assistance»
"""
from __future__ import annotations

_M, _F = "m", "f"

# (voice id, label, gender, accent) per language. Accent words reuse the ElevenLabs catalog's vocabulary so
# `describe()` maps them to the picker's variant names («Español (España)», «English (United Kingdom)»…).
_SHIPPED: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "es": (
        ("13ff5deb-2591-42ad-a356-63a04e524411", "Marcos", _M, "castilian"),
        ("9d8c6b2e-0a23-4a15-ae1b-121d5b5af417", "Nuria", _F, "castilian"),
        ("58e531e3-b212-49df-adee-c335a19c2429", "Gonzalo", _M, "castilian"),
        ("de38f545-c574-44e8-9b54-a7d6fec1c6b1", "Marta", _F, "castilian"),
        ("2fc4f1ec-bfd0-46f1-8e6d-d4279eaaf838", "Mateo", _M, "mexican"),
        ("d46e87a1-7c6d-4b18-9359-926f4a35ffdf", "Andres", _M, "mexican"),
        ("b4b8e2af-6139-466e-a93a-30c20d2e1fc5", "Fernanda", _F, "mexican"),
        ("3597a26f-80ef-4bd5-8101-9699bc764917", "Ximena", _F, "mexican"),
    ),
    "en": (
        ("47c38ca4-5f35-497b-b1a3-415245fb35e1", "Daniel", _M, "american"),
        ("1fcd23d0-bf12-4896-8f60-4f21ef5c9b98", "Austin", _M, "american"),
        ("db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "Skylar", _F, "american"),
        ("0ee8beaa-db49-4024-940d-c7ea09b590b3", "Morgan", _F, "american"),
        ("4bc3cb8c-adb9-4bb8-b5d5-cbbef950b991", "George", _M, "british"),
        ("3d5ce2fb-e56c-42f0-9ed9-4662484063b4", "Toby", _M, "british"),
        ("62ae83ad-4f6a-430b-af41-a9bede9286ca", "Gemma", _F, "british"),
        ("dc30854e-e398-4579-9dc8-16f6cb2c19b9", "Victoria", _F, "british"),
    ),
}

_PINNED: dict[str, str] = {
    "es-ES": "13ff5deb-2591-42ad-a356-63a04e524411",   # Marcos
    "es-419": "2fc4f1ec-bfd0-46f1-8e6d-d4279eaaf838",  # Mateo
    "en-US": "47c38ca4-5f35-497b-b1a3-415245fb35e1",   # Daniel
    "en-GB": "4bc3cb8c-adb9-4bb8-b5d5-cbbef950b991",   # George
}

_DEFAULT_REGION = {"en": "US", "es": "ES"}

_REGION_ACCENTS: dict[str, tuple[str, ...]] = {
    "ES": ("castilian",),
    "419": ("mexican", "latin american"),
    "US": ("american",),
    "GB": ("british",),
}


def _row(lang: str, voice: str, label: str, gender: str, accent: str) -> dict:
    return {"voice": voice, "label": label, "gender": gender, "lang": lang, "accent": accent, "native": True}


def for_language(lang: str) -> list[dict]:
    lang = (lang or "").strip().lower()
    return [_row(lang, *t) for t in _SHIPPED.get(lang, ())]


def all_voices() -> list[dict]:
    return [r for lang in _SHIPPED for r in for_language(lang)]


def pinned_voice(lang: str, region: str = "") -> dict:
    lang = (lang or "").strip().lower()
    region = (region or "").strip().upper() or _DEFAULT_REGION.get(lang, "")
    vid = _PINNED.get(f"{lang}-{region}")
    return next((r for r in for_language(lang) if r["voice"] == vid), {}) if vid else {}


def accents_for(region: str) -> tuple[str, ...]:
    return _REGION_ACCENTS.get((region or "").strip().upper(), ())


def default_voice(lang: str, region: str = "") -> str:
    """The voice for (lang, region) when the operator has not picked one; '' for a language with no table
    (the builder then falls back to the env/plugin default, as before)."""
    pin = pinned_voice(lang, region)
    if pin:
        return pin["voice"]
    rows = for_language(lang)
    for accent in accents_for(region):
        hit = next((r for r in rows if r["accent"] == accent), None)
        if hit:
            return hit["voice"]
    return rows[0]["voice"] if rows else ""


def is_aligned(voice: str, lang: str, region: str = "") -> bool:
    """Is `voice` right for (lang, region)? A voice this table does not know (an operator's own clone, an id
    set by env) is not evidence of a wrong one — unless it is a known voice of ANOTHER language."""
    lang = (lang or "").strip().lower()
    rows = for_language(lang)
    if not rows:
        return True
    here = next((r for r in rows if r["voice"] == voice), None)
    if here is None:
        return not any(r["voice"] == voice for r in all_voices())
    wanted = accents_for(region or _DEFAULT_REGION.get(lang, ""))
    return not wanted or here["accent"] in wanted


__all__ = ["for_language", "all_voices", "pinned_voice", "default_voice", "accents_for", "is_aligned"]
