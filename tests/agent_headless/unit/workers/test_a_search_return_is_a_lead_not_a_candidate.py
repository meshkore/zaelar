#
# test_a_search_return_is_a_lead_not_a_candidate.py — V2-510.
#
# V2-376 already taught the SHEET path that «lo que vuelve de una búsqueda es una PISTA, NO un candidato» and
# marks the row's origin. The NOTE path — the one that actually moves the brain (V2-222 measured a pushed note
# at 3/3 against a rendered prompt line at 0/13) — never learned it, and its imperative ordered the opposite:
# «dáselo con nombre, precio o dato y enlace».
#
# Measured on `cheapest-monitor__us` round 20260830-125532, with V2-508's double sheet already out of the way:
#   offered   → «Best 1440p Monitor 2026…», «The 6 Best Budget And Cheap Monitors of 2026 - RTINGS.com»,
#               «The server returned HTTP 403 Forbidden…», «The web page content you provided contains only
#               RTINGS.com's site navigation…»
#   in sheet  → Dell S2722QC · LG 27UP850N-W · LG 32UN650-W · Samsung ViewFinity S7 · ASUS ProArt PA279CV …
#   delivered → turn 4: a listicle headline.  turn 20: ONE real monitor.
#
# The brain was not disobeying: it was told to name what came back, with price and link, and what came back
# was an article. Raising the cut does not help — they are the first of the DOM, not the relevant ones.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/workers/test_a_search_return_is_a_lead_not_a_candidate.py
#
import pytest

from nucleo.workers import findings


@pytest.fixture(autouse=True)
def _clean():
    findings._HANDED.clear()
    yield
    findings._HANDED.clear()


@pytest.fixture
def pushed(monkeypatch):
    out: list[str] = []
    import voice.brain_notes as bn
    monkeypatch.setattr(bn, "push", lambda text, **k: out.append(text))
    return out


_HEADLINE = "The 6 Best Budget And Cheap Monitors of 2026 - RTINGS.com — a roundup of picks — https://rtings.com/x"


def test_the_note_says_a_page_is_not_a_candidate(pushed):
    assert findings.hand_web_finding("1", _HEADLINE, "monitor barato") is True
    note = pushed[0]
    assert "no es un candidato" in note.lower()
    assert "nunca lo ofrezcas como una opción para elegir" in note.lower()


def test_it_no_longer_orders_the_lead_delivered_with_price_and_link(pushed):
    """The old imperative — «dáselo con nombre, precio o dato y enlace» — applied to WHATEVER came back. That
    single clause is what turned an article headline into a delivered recommendation."""
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    note = pushed[0]
    assert "dáselo con nombre, precio o dato y enlace" not in note, (
        "the unconditional delivery order is the defect; it must not survive")


def test_a_real_answer_is_STILL_ordered_delivered(pushed):
    """The direction that keeps V2-236 alive. That initiative exists because clean data — «Philips
    27E1N1800A/00 — 27\" UHD 4K — 159,00 €» — was dying inside dead workers. Turning the note into «do not
    offer it» would swallow exactly the case it was built for."""
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    note = pushed[0]
    assert "dásela como resultado" in note.lower()
    assert "nombre y su precio" in note.lower()


def test_it_is_still_ONE_instruction_with_the_branch_inside(pushed):
    """V2-226: two orders in one note get resolved by coin flip. The branch lives inside a single imperative,
    and the sentence that can never be true stays forbidden."""
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    note = pushed[0]
    assert note.count("NÓMBRALO EN ESTE TURNO") == 1
    assert "no digas que no hay resultados" in note.lower()


def test_the_finding_itself_still_travels_verbatim(pushed):
    """It carries the text, never a rewrite of it (`observability/evidence.py`'s doctrine)."""
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    assert _HEADLINE in pushed[0]


def test_the_same_return_is_not_a_second_finding(pushed):
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    assert findings.hand_web_finding("1", _HEADLINE, "monitor barato") is False
    assert len(pushed) == 1


def test_the_sheet_path_still_marks_the_origin_too():
    """One lesson, both paths — the whole point. If V2-376's marking is ever dropped from the sheet row, the
    note would be the only place that knows, and the two would disagree about the same return."""
    import inspect
    src = inspect.getsource(findings.hand_search_rows)
    assert '"Origen"' in src and "búsqueda web" in src
