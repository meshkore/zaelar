"""i18n/catalog.py — the LANGUAGES a person can be offered at first run (V2-672).

The operator's brief (2026-09-11): *«pondría un símbolo de una persona hablando para que alguien que no es
capaz de leer lo que pone en la pantalla entienda que tiene que seleccionar el país. Y entonces debajo
pondría la bandera y el nombre del idioma en los 40 idiomas más populares del mundo que sean susceptibles de
utilizar nuestro producto»*, with English and Spanish *«destacados arriba»*.

Why this is NOT `voice/engine/core/langs.py`. That module is the catalog of languages we have a VERIFIED
NATIVE VOICE for, and its own docstring says a language only enters it once that voice exists — which is
correct, and is why it holds exactly two entries. This one answers a different question: what may a person
be OFFERED on the first screen. Everything here is reachable, because `i18n.init.prepare()` generates the
whole UI bundle for a language we do not ship, and the cloud TTS is multilingual; `langs.spec()` falls back
to English for the parts that genuinely need a native voice. Keeping the two apart is the point — merging
them would either shrink the picker to two rows or claim a native voice we do not have.

The FLAG is a deliberate compromise and worth stating: a language is not a country, and several here are
spoken natively in a dozen of them. The flag is an ICON for finding your row at a glance, not a claim about
where the language belongs — which is precisely the job the operator described, for somebody who cannot read
the screen. Where no single flag is defensible the entry still carries the one most people will recognise.

`PINNED` are the two languages the product SHIPS (`i18n.runtime.PRESET`): choosing one of those is instant,
everything else pays a generation. That is a real difference for the person choosing, so the picker says it
by putting them first — not by hiding the rest.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str        # ISO 639-1 (639-2 for Filipino) — the SAME code `stt_language` and the bundles use
    name: str        # English name, for logs and for anybody debugging this
    native: str      # what a speaker of it calls it — the only label the picker shows
    flag: str        # regional-indicator emoji


# The 32 languages the cloud TTS covers end to end, plus 8 more with large speaker populations that still
# get a full UI + brain in their own language (the voice falls back to a multilingual one). Ordered by
# nothing in particular below the two pinned rows — the picker sorts, and any order here would be a claim.
LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "English", "🇺🇸"),
    Language("es", "Spanish", "Español", "🇪🇸"),
    Language("fr", "French", "Français", "🇫🇷"),
    Language("de", "German", "Deutsch", "🇩🇪"),
    Language("it", "Italian", "Italiano", "🇮🇹"),
    Language("pt", "Portuguese", "Português", "🇵🇹"),
    Language("nl", "Dutch", "Nederlands", "🇳🇱"),
    Language("pl", "Polish", "Polski", "🇵🇱"),
    Language("ru", "Russian", "Русский", "🇷🇺"),
    Language("uk", "Ukrainian", "Українська", "🇺🇦"),
    Language("cs", "Czech", "Čeština", "🇨🇿"),
    Language("sk", "Slovak", "Slovenčina", "🇸🇰"),
    Language("hu", "Hungarian", "Magyar", "🇭🇺"),
    Language("ro", "Romanian", "Română", "🇷🇴"),
    Language("bg", "Bulgarian", "Български", "🇧🇬"),
    Language("hr", "Croatian", "Hrvatski", "🇭🇷"),
    Language("sr", "Serbian", "Српски", "🇷🇸"),
    Language("el", "Greek", "Ελληνικά", "🇬🇷"),
    Language("sv", "Swedish", "Svenska", "🇸🇪"),
    Language("da", "Danish", "Dansk", "🇩🇰"),
    Language("no", "Norwegian", "Norsk", "🇳🇴"),
    Language("fi", "Finnish", "Suomi", "🇫🇮"),
    Language("tr", "Turkish", "Türkçe", "🇹🇷"),
    Language("ar", "Arabic", "العربية", "🇸🇦"),
    Language("he", "Hebrew", "עברית", "🇮🇱"),
    Language("fa", "Persian", "فارسی", "🇮🇷"),
    Language("ur", "Urdu", "اردو", "🇵🇰"),
    Language("hi", "Hindi", "हिन्दी", "🇮🇳"),
    Language("bn", "Bengali", "বাংলা", "🇧🇩"),
    Language("ta", "Tamil", "தமிழ்", "🇮🇳"),
    Language("zh", "Chinese", "中文", "🇨🇳"),
    Language("ja", "Japanese", "日本語", "🇯🇵"),
    Language("ko", "Korean", "한국어", "🇰🇷"),
    Language("vi", "Vietnamese", "Tiếng Việt", "🇻🇳"),
    Language("th", "Thai", "ไทย", "🇹🇭"),
    Language("id", "Indonesian", "Bahasa Indonesia", "🇮🇩"),
    Language("ms", "Malay", "Bahasa Melayu", "🇲🇾"),
    Language("fil", "Filipino", "Filipino", "🇵🇭"),
    Language("sw", "Swahili", "Kiswahili", "🇰🇪"),
    Language("af", "Afrikaans", "Afrikaans", "🇿🇦"),
)

# Shipped in the repo — instant, no generation. Mirrors `i18n.runtime.PRESET`; the test keeps them equal so
# the picker cannot promise "instant" for a language we stopped shipping.
PINNED: tuple[str, ...] = ("en", "es")

_BY_CODE = {lang.code: lang for lang in LANGUAGES}


def get(code: str) -> Language | None:
    return _BY_CODE.get((code or "").strip().lower())


def picker() -> list[dict]:
    """The rows the first-run picker paints, PINNED ones first and the rest alphabetical by native name.

    Sorted by the NATIVE name because that is the only label on screen, and sorting by our English name
    would produce an order that looks random to the person reading it.
    """
    pinned = [lang for code in PINNED if (lang := _BY_CODE.get(code))]
    rest = sorted((lang for lang in LANGUAGES if lang.code not in PINNED), key=lambda x: x.native.lower())
    return [{"code": x.code, "name": x.name, "native": x.native, "flag": x.flag,
             "pinned": x.code in PINNED} for x in pinned + rest]


__all__ = ["Language", "LANGUAGES", "PINNED", "get", "picker"]
