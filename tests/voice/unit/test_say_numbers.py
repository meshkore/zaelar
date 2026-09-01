"""V2-538 — figures are made SPEAKABLE at the TTS node, and only there.

The operator, listening to a catamaran search: every price came out wrong. «151.008 €» is read by a TTS as
*one hundred fifty-one point zero zero eight* — it sees a decimal point — and «€» is skipped or lands in
writing order. The text carrying those prices is scraped by the browser extractor and never passes through a
language model, so there is nobody upstream to ask nicely.

The two halves that make it SAFE are the ones under test here: what it rewrites, and what it must leave alone
(an IP, a date, a time, a version). A normaliser that eats an address is worse than one that mispronounces a
price, because the mispronounced price is still recoverable by asking again.
"""
from __future__ import annotations

import asyncio

import pytest

from voice.engine.speech import say_numbers as sn


# ── what it fixes ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,said", [
    ("151.008 €", "151008 euros"),                    # the measured case, verbatim from the operator's sheet
    ("100.000", "100000"),                            # …and the one he named: three digits, a dot, three more
    ("1.500,50 €", "1500,50 euros"),                  # grouping goes, the decimal stays a decimal
    ("1 €", "1 euro"),                                # singular only for an exact 1
    ("el 15% de 40.000 $", "el 15 por ciento de 40000 dólares"),
    ("cuesta 8.2 puntos", "cuesta 8,2 puntos"),        # a decimal written the English way, said in Spanish
])
def test_spanish_figures_are_said_the_way_a_person_says_them(raw, said):
    assert sn.speakable(raw, "es") == said


@pytest.mark.parametrize("raw,said", [
    ("$400", "400 dollars"),                          # the symbol moves BEHIND: nobody says «dollars four hundred»
    ("It costs $151,008.50", "It costs 151008.50 dollars"),   # money's ordinary English shape
    ("$1", "1 dollar"),
    ("1,500 units", "1500 units"),
    ("15% off", "15 percent off"),
    ("€99", "99 euros"),
])
def test_english_figures_are_said_the_way_a_person_says_them(raw, said):
    assert sn.speakable(raw, "en") == said


# ── what it must NOT touch — the half that makes it safe ──────────────────────────────────────────────────
@pytest.mark.parametrize("lang,raw", [
    ("es", "La IP es 192.168.1.1"),        # a group followed by another group is an address, not a figure
    ("en", "192.168.1.1"),
    ("es", "cita el 2026-09-01 a las 15:30"),   # dashes and colons are not separators
    ("en", "v3.16"),                       # a version bound to a word
    ("es", "8,2 de 10"),                   # already correct for its language
])
def test_what_merely_looks_like_a_figure_is_left_alone(lang, raw):
    assert sn.speakable(raw, lang) == raw


def test_an_unknown_language_is_returned_untouched_on_purpose():
    """For a language whose convention we do not know, «1.500» could be fifteen hundred or one point five, and
    the wrong currency word is worse than a symbol the voice may still read acceptably. Adding a language is a
    row in the table, never a function."""
    assert sn.speakable("151.008 €", "fr") == "151.008 €"
    assert sn.speakable("151.008 €", "") == "151.008 €"


def test_the_regexes_are_built_WITHOUT_str_format():
    """A regex is full of literal braces («\\d{1,3}»), so `str.format` reads them as fields and raises KeyError
    — which the fail-open would then swallow, leaving a function that returns every string untouched and looks
    like it works. That happened while writing this module, and it is how the memory's REM synthesis stayed
    silently dead for weeks (`tests/memory/unit/test_rem_prompt.py` guards the same thing)."""
    import inspect
    src = inspect.getsource(sn)
    assert "_GROUPED.format(" not in src and "_FOREIGN_DECIMAL.format(" not in src


def test_a_broken_phrasing_never_costs_the_operator_the_reply():
    """Fail-open: whatever happens in here, something is spoken."""
    assert sn.speakable(None, "es") is None
    assert sn.speakable("", "es") == ""


# ── streaming: a figure split across chunks ───────────────────────────────────────────────────────────────
def _drain(chunks, lang):
    async def go():
        async def src():
            for c in chunks:
                yield c
        return "".join([c async for c in sn.stream(src(), lang)])
    return asyncio.run(go())


def test_a_figure_split_across_chunks_is_still_fixed():
    """THE reason this is not a plain `map`: the node is fed chunks, so «151.008 €» arrives as «151.» + «008 €»
    and no regex would ever see it whole. The tail is held back and flushed."""
    assert _drain(["El barco cuesta 151.", "008 € y me gusta"], "es") == "El barco cuesta 151008 euros y me gusta"
    assert _drain(["$", "400"], "en") == "400 dollars"


def test_only_the_trailing_figure_is_held_back_never_the_sentence():
    """Holding back more than the tail of a number would delay the first audio, which is the one thing this may
    not cost."""
    assert sn.safe_cut("Todo listo, cuesta 151.") == len("Todo listo, cuesta ")   # holds "151."
    assert sn.safe_cut("Todo listo.") == len("Todo listo.")       # a full stop is not part of a figure
    assert sn.safe_cut("Hecho. ") == len("Hecho. ")               # nothing numeric: nothing held
    # The trailing SPACE goes with the figure, so «400 » + «€» still meet in the same buffer.
    assert sn.safe_cut("cuesta 400 ") == len("cuesta ")
    # …and a symbol is never cut away from its number: «$» + «400» used to come out as «$400».
    assert sn.safe_cut("$400") == 0 and sn.safe_cut("$") == 0
    long = "hola " + "1" * 80
    assert len(long) - sn.safe_cut(long) <= sn._MAX_HOLD, "una cola patológica no puede crecer sin freno"


def test_nothing_is_lost_when_the_stream_ends_mid_figure():
    assert _drain(["quedan 100.000"], "es") == "quedan 100000"
    assert _drain(["nada que ver"], "es") == "nada que ver"


# ── wiring: it has to be the TTS node, and NOT the transcription one ──────────────────────────────────────
def test_it_is_wired_into_the_tts_node_and_the_subtitles_are_left_alone():
    """The TTS node is the one place every spoken path converges on (reply, say(), filler, proactive notice), so
    a price cannot slip through by taking another road. Subtitles and the chat wall go through
    `transcription_node` and must keep showing «151.008 €», which is what the operator wants to READ."""
    import pathlib
    src = pathlib.Path("voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert "def tts_node(self, text, model_settings):" in src
    assert "tts_node_speaking_figures" in src
    tn = src[src.index("def transcription_node("):src.index("def tts_node(")]
    assert "say_numbers" not in tn, "los subtítulos se leen, no se pronuncian: no se tocan"
