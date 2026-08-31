#
# test_what_counts_is_not_what_it_brings.py — V2-511.
#
# `_maybe_hand_web` pushes the RAW text of any web step that is not `is_error` — and a tool that successfully
# returns a refusal is not `is_error` by that test. Measured on `cheapest-monitor__us` round 20260830-130649,
# with the sheet EMPTY (`results_sheet: []`, `in_sheet: 0`, `shown_to_model: false`) and 17 notes offered to
# the brain. The seventeen, verbatim from the report — this file's corpus:
#
#   7 HTTP errors and the worker's own refusals   («The server returned HTTP 404 Not Found…»)
#   11 the CLI's own SEARCH ENVELOPE             («Web search results for query: … Links: [{"title":…»)
#   0 listings.
#
# The judge had spent four rounds filing «presents irrelevant candidates» [high]. The agent was not choosing
# badly — that is what it was handed.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/workers/test_what_counts_is_not_what_it_brings.py
#
import pytest

from nucleo.workers import findings

# ── the real corpus, copied from the round's report ──────────────────────────────────────────────────────
_JUNK = [
    "The server returned HTTP 404 Not Found. The response body was not retrieved. If this URL requires "
    "authentication, use an authenticated fetch.",
    "The provided page content does not actually include the 1440p ranking list itself. It only shows: - Site "
    "navigation",
    "Based on the content provided, I'm unable to summarize the monitor's specifications or verdict.",
    'Web search results for query: "best 1440p monitors for work under $350 2026" Links: [{"title":"Best 1440p '
    'high refresh", "url":"https://example.com/a"}]',
    "The server returned HTTP 403 Forbidden. The response body was not retrieved.",
    "The page content you provided is only the TextWordCount site navigation/header",
    "Here are the six monitors from the article. Note: exact per-monitor prices are not stated",
]

# The case V2-236 was BUILT for — clean data dying inside a worker that crashed before delivering.
_REAL = [
    'Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €',
    "Alurin CoreVision 27\" IPS 4K Freesync — 149,99 €",
    "Cambria Hotel Warehouse District — from €122 — https://booking.example/cambria",
    "Fontanería Bilbao — https://fontaneros.example/bilbao",
]


@pytest.mark.parametrize("text", _JUNK)
def test_something_that_only_RECOUNTS_is_not_a_finding(text):
    assert findings.looks_like_a_finding(text) is False, text[:60]


@pytest.mark.parametrize("text", _REAL)
def test_something_that_BRINGS_a_hard_datum_still_is(text):
    """The direction that decides. A filter that drops everything would pass every case above, and would
    silently undo the whole reason V2-236 exists."""
    assert findings.looks_like_a_finding(text) is True, text[:60]


def test_the_envelope_is_caught_by_STRUCTURE_not_by_its_english():
    """The header is written differently by each CLI, and chasing that wording is the race V2-364 measured
    as unwinnable. What gives an envelope away is the JSON array of links inside it."""
    assert findings.looks_like_a_finding(
        'Resultados de búsqueda para "monitor barato" Enlaces: [{"title":"x","url":"https://a.example/b"}]'
    ) is False


def test_an_envelope_beats_a_url_it_happens_to_contain():
    """Order matters: an envelope is full of links, so testing for a URL first would let all eleven through."""
    assert findings.looks_like_a_finding(
        'Web search results for query: "x" Links: [{"url":"https://a.example/b"}] https://c.example/d'
    ) is False


# ── the wiring: the filter has to run on the real push path ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean():
    findings._HANDED.clear()
    yield
    findings._HANDED.clear()


@pytest.fixture
def pushed(monkeypatch):
    out: list = []
    import voice.brain_notes as bn
    monkeypatch.setattr(bn, "push", lambda text, **k: out.append(text))
    return out


def test_hand_web_finding_drops_the_junk(pushed):
    for j in _JUNK:
        assert findings.hand_web_finding("1", j, "monitor barato") is False
    assert pushed == [], "not one of the seventeen should reach the conversation"


def test_hand_web_finding_still_pushes_a_real_one(pushed):
    assert findings.hand_web_finding("1", _REAL[0], "monitor barato") is True
    assert len(pushed) == 1 and "Philips" in pushed[0]


def test_a_dropped_one_does_not_burn_the_dedup_slot(pushed):
    """A rejected text must not be remembered as handed.

    The hazard is concrete and it is the SIGNATURE: `_HANDED` keys on `body[:200]`, so two long texts that
    share their first 200 characters are the same entry. A page fetched twice does exactly that — the first
    read all navigation and no data, the second the same header with the listing underneath. If the barren
    read burned the slot, the good one would be dropped as «already handed» and nobody would ever know.
    Two short strings can never show this: their signature IS the whole string."""
    prefijo = "Monitores 27 pulgadas · comparativa · " + ("navegación " * 20)
    assert len(prefijo) > 200
    esteril = prefijo + "y aquí no hay ni precios ni fichas."
    bueno = prefijo + "Dell S2722QC — 279,99 € — https://tienda.example/dell-s2722qc"
    assert esteril[:200] == bueno[:200], "el caso exige que compartan la FIRMA"

    assert findings.hand_web_finding("1", esteril, "monitor") is False
    assert findings.hand_web_finding("1", bueno, "monitor") is True, (
        "el descartado se quedó con la firma y se comió el hallazgo bueno")
    assert len(pushed) == 1
