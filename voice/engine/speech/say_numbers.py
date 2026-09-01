"""Make figures SPEAKABLE right before synthesis — the last chokepoint before the voice (V2-538).

The operator, listening to a catamaran search read out loud: every price came out wrong. «151.008 €» and
«100.000» are not exotic — they are what a listing page contains, and the text that carries them **never
passed through a language model**: it was scraped by the browser extractor and handed straight to the sheet
and to the voice. So there is nobody upstream to ask nicely; the fix has to be a transformation, and the only
place that sees EVERYTHING spoken — a generated reply, a `say()`, the lead-in filler, a proactive notice — is
the TTS node.

WHAT ACTUALLY BREAKS, and it is two things, not one:

  · THE GROUPING SEPARATOR. A TTS reading «151.008» sees a decimal point and says *one hundred fifty-one point
    zero zero eight*. Which character groups and which one decimates is a property of the LANGUAGE (dot groups
    in Spanish, comma groups in English) — that is why this is parameterised by language rather than guessed.
  · THE SYMBOL. «€» is skipped or mispronounced by several voices, and when it IS read it lands in writing
    order («dollars four hundred»), which is not how anyone says it. The word goes AFTER the number.

WHAT IT DELIBERATELY DOES NOT DO. It does not spell numbers out in words: a Spanish/English number speller is
a per-language component with its own gender and agreement rules, and every TTS already reads a plain integer
correctly. Removing the grouping is enough, and it is the cheap half.

UNKNOWN LANGUAGES ARE LEFT ALONE, ON PURPOSE. For a language whose convention we do not know, "1.500" could be
fifteen hundred or one point five — and writing the wrong currency word is worse than leaving a symbol the
voice may still read acceptably in its own tongue. Today the voice catalog is es+en (`langs.supported()`);
a third language adds a row to `_LANG`, not a function.

Pure and dependency-free so it can be measured without a browser, a provider or a session.
"""
from __future__ import annotations

import re

# Per language: which char groups thousands, which one decimates, and how each symbol is SAID.
# `one` is used only for an exact «1» — «1,50 €» stays plural, which is what a person says.
_LANG: dict[str, dict] = {
    "es": {
        "group": ".", "decimal": ",",
        "symbols": {"€": ("euro", "euros"), "$": ("dólar", "dólares"), "£": ("libra", "libras"),
                    "¥": ("yen", "yenes"), "%": ("por ciento", "por ciento")},
    },
    "en": {
        "group": ",", "decimal": ".",
        "symbols": {"€": ("euro", "euros"), "$": ("dollar", "dollars"), "£": ("pound", "pounds"),
                    "¥": ("yen", "yen"), "%": ("percent", "percent")},
    },
}

# A number to fix is 1-3 digits followed by one or more groups of EXACTLY three. The lookarounds are what keep
# it from eating things that merely look alike: «192.168.1.1» fails (the group is followed by another dot),
# «3.16» fails (two digits), «2026-09-01» fails (dashes), «15:30» fails (colon).
#
# ⚠️ These are built with `.replace`, NEVER `str.format`: a regex is FULL of literal braces («\d{1,3}»), so
# `.format` reads them as fields and raises KeyError — which the fail-open below would then swallow, leaving
# a function that returns every string untouched and looks like it works. That is exactly how the memory's
# REM synthesis stayed silently dead for weeks (see `tests/memory/unit/test_rem_prompt.py`), and it happened
# here too, caught only by running it against real strings.
# The trailing lookahead rejects ANOTHER separator+digits (that is «192.168.1.1», not a figure) while
# still allowing the DECIMAL part — «$151,008.50» is the ordinary way money is written in English, and
# a plain `(?![\d.,])` left its grouping comma in place.
_GROUPED = r"(?<![\d.,])\d{1,3}(?:SEP\d{3})+(?!SEP?\d)"
# A decimal written with the OTHER language's separator: 1-2 fractional digits, never 3 (that is a group).
_FOREIGN_DECIMAL = r"(?<![\w.,])(\d+)SEP(\d{1,2})(?![\d.,])"


def _fix_numbers(text: str, group: str, decimal: str) -> str:
    """Drop the grouping separator and normalise a decimal written the other way round."""
    sep = re.escape(group)
    text = re.sub(_GROUPED.replace("SEP", sep), lambda m: m.group(0).replace(group, ""), text)
    return re.sub(_FOREIGN_DECIMAL.replace("SEP", sep), "\\1" + decimal + "\\2", text)


def _fix_symbols(text: str, symbols: dict[str, tuple[str, str]]) -> str:
    """Say the symbol as a word, AFTER its number — «€400» and «400 €» both become «400 euros»."""
    for sym, (one, many) in symbols.items():
        s = re.escape(sym)
        # symbol BEFORE the number (English writing order) → move the word behind it
        text = re.sub(rf"{s}\s?(\d+(?:[.,]\d+)*)",
                      lambda m, one=one, many=many: f"{m.group(1)} {one if m.group(1) == '1' else many}", text)
        # symbol AFTER the number (Spanish writing order) → just replace it
        text = re.sub(rf"(\d+(?:[.,]\d+)*)\s?{s}",
                      lambda m, one=one, many=many: f"{m.group(1)} {one if m.group(1) == '1' else many}", text)
    return text


def speakable(text: str, lang: str) -> str:
    """The spoken form of `text`. Unknown language → returned untouched (see the module docstring)."""
    spec = _LANG.get((lang or "").split("-")[0].lower())
    if not spec or not text:
        return text
    try:
        return _fix_symbols(_fix_numbers(text, spec["group"], spec["decimal"]), spec["symbols"])
    except Exception:                      # never let a phrasing detail cost the operator the whole reply
        return text


# ── streaming ────────────────────────────────────────────────────────────────────────────────────────────
# The TTS node is fed CHUNKS, so «151.008 €» can arrive as «151.» + «008 €» and no regex would ever see it
# whole. We hold back only the trailing run that could still be part of a figure — a handful of characters,
# so the first audio is not delayed in any measurable way — and flush it when the stream ends.
_MAX_HOLD = 24                              # a pathological tail must never grow unbounded
# The tail is held ONLY if it can still be the head of a figure: digits (with their separators, and an
# optional trailing space so «400 » + «€» survives) or a lone currency symbol waiting for its number.
# ⚠️ A blanket "hold every char that could appear in a figure" also holds a SENTENCE-FINAL FULL STOP — and
# that period is exactly what the TTS sentence tokenizer needs to close a segment, so holding it delays the
# audio of the last sentence until the stream ends. Punctuation with no digit near it is not a figure.
# It must cover the figure WHOLE — symbol included, on either side. Cutting between «$» and «400» hands
# the symbol over on its own and the number arrives with nothing to attach to: «$400» came out as «$400».
_TAIL_RE = re.compile(r"(?:[€$£¥%]\s?)?\d[\d.,]*(?:\s?[€$£¥%])?\s?$|[€$£¥%]\s?$")


def safe_cut(buf: str) -> int:
    """Index up to which `buf` can be emitted now; the rest may still be the head of a figure."""
    m = _TAIL_RE.search(buf)
    if not m or len(buf) - m.start() > _MAX_HOLD:
        return len(buf)
    return m.start()


async def stream(source, lang: str):
    """Wrap an async iterable of text chunks, yielding their spoken form."""
    tail = ""
    async for chunk in source:
        buf = tail + (chunk or "")
        cut = safe_cut(buf)
        out, tail = buf[:cut], buf[cut:]
        if out:
            yield speakable(out, lang)
    if tail:
        yield speakable(tail, lang)


def tts_node_speaking_figures(agent, default_node, text, model_settings, lang: str):
    """Drop-in for `Agent.tts_node`: same node, fed text a person would read out loud."""
    return default_node(agent, stream(text, lang), model_settings)
