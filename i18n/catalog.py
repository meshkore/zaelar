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


@dataclass(frozen=True)
class Variant:
    """A REGIONAL variant of a shipped language (V2-734).

    The operator, after hearing a Peruvian voice read his Castilian (2026-09-20): *«no es lo mismo el
    español de España que el español latino. Así que si quieres, en la selección de idiomas pon inglés de
    Estados Unidos, inglés de Reino Unido, español de España o español latino. Eso nos ayudará a elegir
    por defecto la voz más adecuada.»* — which is exactly what it is for, and the whole of what it is for.

    A variant is NOT a language here. It shares the bundle, the STT code, the memory's canonical language
    and everything else with its `base`; the only thing it decides is which ACCENT the default voice
    should have. Making it a language would mean a second Spanish UI to generate and keep in step, for a
    difference the interface does not have.
    """
    code: str        # "es-419" — what the picker sends back and what identifies the row
    base: str        # "es" — the language everything downstream uses, unchanged
    region: str      # "419" — resolved to a set of accents by the VOICE catalog, not by this module
    name: str        # English name, for logs
    native: str      # what a speaker calls it — the only label on the picker
    flag: str


# Only the SHIPPED languages have variants, and only where the difference is one a listener hears
# immediately. The flag follows this module's existing compromise — an icon for finding your row, not a
# claim about where a language belongs — so Latin America carries the flag of its largest population
# rather than a globe nobody scans as "Spanish".
VARIANTS: tuple[Variant, ...] = (
    Variant("en-US", "en", "US",  "English (United States)", "English (US)", "🇺🇸"),
    Variant("en-GB", "en", "GB",  "English (United Kingdom)", "English (UK)", "🇬🇧"),
    Variant("es-ES", "es", "ES",  "Spanish (Spain)", "Español (España)", "🇪🇸"),
    Variant("es-419", "es", "419", "Spanish (Latin America)", "Español (Latinoamérica)", "🇲🇽"),
)

_BY_CODE = {lang.code: lang for lang in LANGUAGES}
_VARIANTS_BY_BASE: dict[str, list[Variant]] = {}
for _v in VARIANTS:
    _VARIANTS_BY_BASE.setdefault(_v.base, []).append(_v)


def split_locale(code: str) -> tuple[str, str]:
    """`"es-419"` → `("es", "419")`, `"es"` → `("es", "")`.

    THE ONE PLACE that knows a picker code may carry a region. Everything downstream — the bundle, the STT
    language, `ZAELAR_LANGUAGE`, the memory's canonical language — takes the base and has never needed to
    know the rest; the region is persisted beside it and read only when a voice is being chosen.
    """
    raw = (code or "").strip()
    if "-" not in raw:
        return raw.lower(), ""
    base, _, region = raw.partition("-")
    return base.strip().lower(), region.strip().upper()


def get(code: str) -> Language | None:
    """The language for a code, accepting a regional variant (`es-419` resolves to Spanish)."""
    base, _ = split_locale(code)
    return _BY_CODE.get(base)


def variant(code: str) -> Variant | None:
    """The variant row for a full code, or None for a bare language."""
    raw = (code or "").strip()
    return next((v for v in VARIANTS if v.code.lower() == raw.lower()), None)


def picker() -> list[dict]:
    """The rows the first-run picker paints, PINNED ones first and the rest alphabetical by native name.

    Sorted by the NATIVE name because that is the only label on screen, and sorting by our English name
    would produce an order that looks random to the person reading it.
    """
    # V2-734 — a shipped language is offered as its REGIONAL VARIANTS, because that is the choice that
    # decides which voice speaks to you. A language with no variants declared is offered as itself.
    pinned: list[object] = []
    for code in PINNED:
        pinned.extend(_VARIANTS_BY_BASE.get(code) or [lang for lang in [_BY_CODE.get(code)] if lang])
    rest = sorted((lang for lang in LANGUAGES if lang.code not in PINNED), key=lambda x: x.native.lower())
    return [{"code": x.code, "name": x.name, "native": x.native, "flag": x.flag,
             "base": getattr(x, "base", "") or x.code, "region": getattr(x, "region", ""),
             "pinned": (getattr(x, "base", "") or x.code) in PINNED} for x in pinned + rest]


__all__ = ["Language", "LANGUAGES", "PINNED", "Variant", "VARIANTS", "get", "variant",
           "split_locale", "picker"]
