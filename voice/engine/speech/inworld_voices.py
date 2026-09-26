"""Inworld voice catalog — which voice speaks each language variant (V2-774).

Same contract as `elevenlabs_voices.py` (rows `{voice, label, gender, lang, accent, native}`, a pinned default
per variant, `for_language` / `default_voice` / `pinned_voice`), so `voices.py` can treat both providers the
same way. What differs is where the list comes from, and that is a property of the provider:

  · Inworld identifies a voice by its NAME (`"Alvaro"`), not by an opaque id, and the built-in voices are the
    same for every account. `GET /tts/v1/voices` returned 282 of them on 2026-09-26 — 34 Spanish, 159 English —
    each tagged with ONE language. So a shipped table is not a stale copy of something account-specific: it is
    the catalog, and it works offline, before any key exists, and on a cold boot with no network.
  · Because every voice is native to exactly one language, a picker built from this table cannot offer a
    wrong-language voice, and there is no "multilingual fallback" tier to reason about (unlike ElevenLabs).

HOW THE DEFAULTS WERE CHOSEN — measured, not by list order (2026-09-26). Each candidate synthesised the same
conversational line with `inworld-tts-2`; the audio was then (a) transcribed by Deepgram nova-3 — every pick
scored WER 0 — and (b) run through Inworld STT's voice profile, which reports the accent, gender and age a
third party hears. The rule is the one the ElevenLabs pins follow: an ADULT voice whose use case is
CONVERSATION (an assistant talks, it does not narrate), native to the variant, with the cleanest accent score:

  es-ES  Alvaro    accent es-ES 0.96 · adult 0.94 · male 1.00   (Sergio scored es-ES 0.52 — half "mul")
  es-419 Salvador  catalog: Mexican Spanish · the only candidate the profile heard any es-MX in
  en-US  Reed      accent en-US 0.92 · adult 0.84               (Dennis: gender only 0.73 male)
  en-GB  Freddie   accent en-GB 0.91 · catalog: «ideal for conversational assistants»

⚠️ The profile's accent classifier is weak on LATIN AMERICAN Spanish (it labelled explicitly Mexican voices
es-ES, and two "neutral" ones it-IT), so for es-419 the catalog description decided, not the score.
"""
from __future__ import annotations

_M, _F = "m", "f"

# (voice, gender, accent) per language — the built-in voices that suit an assistant. Accent words reuse the
# ElevenLabs catalog's vocabulary (`_REGION_ACCENTS`) so a region narrows both providers the same way.
_SHIPPED: dict[str, tuple[tuple[str, str, str], ...]] = {
    "es": (
        ("Alvaro", _M, "castilian"), ("Joaquin", _M, "castilian"), ("Nacho", _M, "castilian"),
        ("Borja", _M, "castilian"), ("Sergio", _M, "castilian"), ("Mercedes", _F, "castilian"),
        ("Marta", _F, "castilian"), ("Rocio", _F, "castilian"),
        ("Salvador", _M, "mexican"), ("Bruno", _M, "mexican"), ("Maximiliano", _M, "mexican"),
        ("Itzel", _F, "mexican"), ("Paloma", _F, "mexican"), ("Sofia", _F, "latin american"),
        ("Diego", _M, "latin american"), ("Rafael", _M, "latin american"),
    ),
    "en": (
        ("Reed", _M, "american"), ("Dennis", _M, "american"), ("Evan", _M, "american"),
        ("Derek", _M, "american"), ("Ashley", _F, "american"), ("Kelsey", _F, "american"),
        ("Lauren", _F, "american"),
        ("Freddie", _M, "british"), ("Felix", _M, "british"), ("Duncan", _M, "british"),
        ("Alistair", _M, "british"), ("Sophie", _F, "british"), ("Eleanor", _F, "british"),
    ),
}

_PINNED: dict[str, str] = {"es-ES": "Alvaro", "es-419": "Salvador", "en-US": "Reed", "en-GB": "Freddie"}

# A language with no region chosen speaks its first variant — same as the ElevenLabs catalog.
_DEFAULT_REGION = {"en": "US", "es": "ES"}

_REGION_ACCENTS: dict[str, tuple[str, ...]] = {
    "ES": ("castilian",),
    "419": ("latin american", "mexican"),
    "US": ("american",),
    "GB": ("british",),
}


def _row(lang: str, voice: str, gender: str, accent: str) -> dict:
    return {"voice": voice, "label": voice, "gender": gender, "lang": lang, "accent": accent, "native": True}


def for_language(lang: str) -> list[dict]:
    """The voices native to `lang`, empty for a language this table does not cover (the builder then keeps
    the plugin's own default rather than a wrong-language voice)."""
    lang = (lang or "").strip().lower()
    return [_row(lang, *t) for t in _SHIPPED.get(lang, ())]


def pinned_voice(lang: str, region: str = "") -> dict:
    """The pinned row for (lang, region), {} when that variant has no pin."""
    lang = (lang or "").strip().lower()
    region = (region or "").strip().upper() or _DEFAULT_REGION.get(lang, "")
    name = _PINNED.get(f"{lang}-{region}")
    return next((r for r in for_language(lang) if r["voice"] == name), {}) if name else {}


def accents_for(region: str) -> tuple[str, ...]:
    return _REGION_ACCENTS.get((region or "").strip().upper(), ())


def default_voice(lang: str, region: str = "") -> str:
    """The voice for (lang, region) when the operator has not picked one; '' when we know none."""
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
    """Is `voice` right for (lang, region)? Native to the language, and — once a region is chosen — of an
    accent that region prefers. A language this table does not cover keeps whatever is set."""
    rows = for_language(lang)
    if not rows:
        return True
    here = next((r for r in rows if r["voice"] == voice), None)
    if here is None:
        return False
    wanted = accents_for(region or _DEFAULT_REGION.get((lang or "").strip().lower(), ""))
    return not wanted or here["accent"] in wanted


__all__ = ["for_language", "pinned_voice", "default_voice", "accents_for", "is_aligned"]
