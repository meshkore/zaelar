"""V2-649 — a FILENAME is not read out character by character, and the chat keeps the precise one.

Measured live (session `653f8346`, 2026-09-10, 00:37-00:43): the torrent client declined an `.mkv` and its
refusal named the file, so the voice said

    «Minions.and.Monsters.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv»

three times, dot by dot — «parece un robot… se encalla, hay cosas que no entiende, se corta». The string is
a fact about a file and the SCREEN wants it verbatim, so the repair is at the TTS node, the one place that
sees everything spoken and nothing written.

The two halves under test are the same two the figure sibling has: what it rewrites, and — the half that
makes it safe — what it must leave completely alone. A normaliser that eats a word it merely SUSPECTED is
worse than one that reads a filename badly: the bad reading is recoverable by asking again, the eaten word
is gone and the operator never learns it was said.
"""
from __future__ import annotations

import asyncio

import pytest

from voice.engine.speech import say_names as sname
from voice.engine.speech import say_numbers as sn


# ── what it says out loud ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,said", [
    # The measured incident, verbatim from the operator's own session.
    ("Minions.and.Monsters.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv", "Minions and Monsters 2026"),
    ("The.Matrix.1999.1080p.BluRay.x264-AMIABLE.mkv", "The Matrix 1999"),
    # The audio layout leaves a stray digit («7.1» → `7`, `1`) and the release group trails the last tag.
    ("Terminator.2.Judgment.Day.1991.2160p.UHD.BluRay.x265.10bit.HDR.DTS-HD.MA.TrueHD.7.1-SWTYBLZ.mkv",
     "Terminator 2 Judgment Day 1991"),
    # An ordinary file nobody would call a release still loses its extension and its underscores.
    ("informe_anual_2025.pdf", "informe anual 2025"),
    ("Acta-de-la-reunion.docx", "Acta de la reunion"),
])
def test_a_filename_is_said_as_a_title(raw, said):
    assert sname.speakable_names(raw) == said


def test_the_language_of_the_copy_survives_the_encoding_tags():
    """«en castellano» is what the operator ASKED for, so it is not noise — dropping it answers a question
    he can no longer check.

    ⚠️ The first version of this case put «Castellano» in the middle, where it survives for a reason that has
    nothing to do with the rule (only a TRAILING token is dropped for following junk) — a disarm of the
    allowlist stayed green. The word has to sit exactly where the release group sits, or this measures
    position instead of policy."""
    assert sname.speakable_names("Peli.2026.1080p.Castellano.mkv") == "Peli 2026 Castellano"
    assert sname.speakable_names("Peli.2026.720p.HDTV.Castellano.x264-GRUPO.mp4") == "Peli 2026 Castellano"


def test_an_all_technical_name_says_the_stem_rather_than_nothing():
    """Saying nothing at all is the failure that loses the fact — falling back to the stem is not."""
    assert sname.speakable_names("1080p.x265.AAC.mkv") == "1080p x265 AAC"


def test_a_link_is_said_as_its_host():
    assert sname.speakable_names("mira https://www.thepiratebay.org/torrent/1/A_B-C.mkv y listo") == \
        "mira thepiratebay.org y listo"


def test_a_rule_of_symbols_is_not_spelled_out():
    assert sname.speakable_names("total ----- 40") == "total 40"


# ── what it must not touch, which is the half that makes it safe ─────────────────────────────────────────
@pytest.mark.parametrize("raw", [
    "192.168.1.1",                       # an address
    "coches.net tiene coches",           # a DOMAIN: a person really does say «coches punto net»
    "escríbeme a hola@zaelar.com",       # …and so does an email address
    "2026-09-01",                        # a date
    "a las 15:30",                       # a time
    "cuesta 8,20",                       # a decimal
    "no lo reproduce.",                  # a sentence-final full stop is not a filename
    "el archivo es de 4.5 GB",           # a figure with a unit
])
def test_what_is_not_a_filename_is_returned_untouched(raw):
    assert sname.speakable_names(raw) == raw


def test_the_figure_half_still_does_its_job(monkeypatch):
    """A regression fence on the sibling: the names pass runs FIRST and must not eat what V2-538 fixed."""
    assert sn.speakable("cuesta 151.008 €", "es") == "cuesta 151008 euros"
    assert sn.speakable("It costs $151,008.50", "en") == "It costs 151008.50 dollars"


def test_a_release_name_never_reaches_the_figure_regexes_as_money():
    """The order is load-bearing: «2026.1080p» and «AAC5.1» are digit runs a currency pass would mangle."""
    assert sn.speakable("«The.Matrix.1999.1080p.BluRay.x264-AMIABLE.mkv»", "es") == "«The Matrix 1999»"


def test_an_unknown_language_still_gets_the_names(monkeypatch):
    """The deliberate asymmetry: which char groups thousands is a property of a LANGUAGE, `.mkv` is not.
    The figure half must bail on an unknown language; this one has nothing to be unsure about."""
    said = sn.speakable("The.Matrix.1999.1080p.x264.mkv cuesta 1.500", "sw")
    assert said.startswith("The Matrix 1999")
    assert "1.500" in said, "the figure half must still leave an unknown language's number alone"


def test_it_fails_open(monkeypatch):
    monkeypatch.setattr(sname, "_URL", None)          # any explosion inside must cost the phrasing, not the reply
    assert sname.speakable_names("hola qué tal") == "hola qué tal"


# ── streaming: the node is fed CHUNKS, and the evidence arrives LAST ─────────────────────────────────────
_SENTENCE = ("«Minions.and.Monsters.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv» es un .mkv "
             "y no lo reproduce.")


def _streamed(size: int) -> str:
    async def go():
        async def src():
            for i in range(0, len(_SENTENCE), size):
                yield _SENTENCE[i:i + size]
        return "".join([c async for c in sn.stream(src(), "es")])
    return asyncio.run(go())


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 7, 13, 40, 400])
def test_no_chunk_size_lets_the_encoding_tags_be_spoken(size):
    """The REPORTED failure, at every cut: held only on a visible interior dot, «Mi» «nio» «ns.» were
    already spoken before the first dot proved anything. Whatever the boundaries, the tags never survive."""
    said = _streamed(size)
    for tag in ("1080p", "WEBRip", "AAC5", "10bits", "x265", "Rapta", ".mkv»"):
        assert tag not in said, f"chunked at {size}, «{tag}» reached the voice"


@pytest.mark.parametrize("size", [2, 4, 5, 7, 13, 40, 400])
def test_and_the_title_comes_out_whole(size):
    assert _streamed(size) == "«Minions and Monsters 2026» es un .mkv y no lo reproduce."


@pytest.mark.parametrize("size,said", [
    (1, "«Minions.and.Monsters.2026» es un .mkv y no lo reproduce."),
    (3, "«Minions.and Monsters 2026» es un .mkv y no lo reproduce."),
])
def test_the_known_limit_degrades_instead_of_breaking(size, said):
    """A chunk ending EXACTLY on a dot is indistinguishable from a sentence ending, so that prefix goes out
    untransformed. Written down rather than hidden: the tags are still gone, which is what was reported."""
    assert _streamed(size) == said


def test_a_pathological_run_with_no_whitespace_is_not_held_forever():
    buf = "x" * (sname.NAME_MAX_HOLD + 50)
    assert sn.safe_cut(buf) == len(buf)


def test_a_finished_word_is_emitted_without_waiting():
    """The counterweight: holding the CURRENT word must not become holding the sentence."""
    assert sn.safe_cut("ya está listo ") == len("ya está listo ")
