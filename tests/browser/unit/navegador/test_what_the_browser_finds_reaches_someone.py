"""V2-223 — the browser found the hotel and nobody was ever told.

`hotel-under-15-days`, sandbox `20260820-194231`, from the stream:

    19:44:00  navigate → booking.com/searchresults?ss=Sevilla&checkin=2026-08-28&checkout=2026-09-01&group_adults=2
    19:44:39  extract  → 1 result, and it was an ad: «Experiencia Premium en el Teatro Flamenco Sevilla», € 25
    19:44:47  pivoted to Google Hotels by itself
    19:45:29  extract  → «Exe Sevilla Macarena», «65 €», with a URL
    19:45:45  turn 7   → «¡De nada! Sigo pendiente y te digo en cuanto tenga algo.»

Sixteen seconds between finding it and denying it. The turn's system prompt contains none of «Exe Sevilla»,
«Macarena» or «65 €», and the run reported `missing_signals: ['widget']`, so the results sheet was empty too —
and V2-257 later found out WHY it was empty: nothing in the engine ever wrote to it from a browser errand.
The listing existed only in the worker's stdout: `set_results` was called exclusively by
`dispatch._finalize_web`, at the END of the session, re-scraping whatever page was on screen by then.

Two properties, and the second is why this is not simply «announce whatever it scraped»: the FIRST extraction of
the case was an ad, so an order to announce would have offered a €25 flamenco show as the four-star hotel. The
note hands the facts over and names the test; the judgement stays where judgement belongs.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks

HOTEL = [{"title": "Exe Sevilla Macarena", "price": "65 €", "url": "https://www.google.com/travel/hotels/x"}]
AD = [{"title": "Experiencia Premium en el Teatro Flamenco Sevilla", "price": "€ 25", "url": "https://x.example"}]


@pytest.fixture
def task():
    tid = tasks.create("Busca hoteles de 4 estrellas para 2 personas, 4 noches, en Sevilla")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    yield tid
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()


def test_what_was_extracted_becomes_a_FACT_on_the_task(task):
    """Renamed in V2-257, because the old name (`..._lands_in_the_results_sheet`) promised a surface this
    assertion never touched: `tasks.get()` is the browser TASK, not the sheet. The mismatch was not cosmetic —
    it is exactly how `missing_signals: ['widget']` kept being read as an extraction failure while the sheet had
    no door at all. What this still guards is the FACT: `has_results` is what lets a turn say «it already
    brought something» instead of choosing between «alive» and «stuck» (V2-192/V2-200). The delivery to the
    sheet is node 4.35."""
    act_api._hand_over(task, HOTEL)
    assert (tasks.get(task) or {}).get("results", {}).get("items") == HOTEL


def test_and_it_reaches_the_conversation_by_the_path_that_works(task):
    """Pushed note, measured 3/3 in this same case, rather than a prompt status line, measured 0/13."""
    act_api._hand_over(task, HOTEL)
    note = brain_notes.drain()
    assert len(note) == 1
    assert "Exe Sevilla Macarena" in note[0] and "65 €" in note[0]
    assert "https://www.google.com/travel/hotels/x" in note[0]


def test_the_note_names_the_TEST_instead_of_ordering_an_announcement(task):
    """The €25 flamenco show is the counter-example that shapes the wording: an unconditional «tell him this»
    would have delivered an ad as the answer."""
    act_api._hand_over(task, AD)
    note = brain_notes.drain()[0]
    assert "si responde a lo que pidió el operador" in note
    assert "di por qué no sirve" in note


def test_it_carries_ONE_order_with_the_fork_inside_it(task):
    """V2-226. The first version said «if it answers, give it; if not, don't offer it as a result; but then don't
    say you're still searching either», and the first clean round measured what three clauses do: the browser had
    extracted the flamenco ad and the turn said «se ha quedado a medias y no ha llegado a darme resultados» — it
    obeyed the middle clause and dropped the last. Same shape V2-224 had just measured on the ended-tasks block.

    So there is ONE imperative, and the sentence that can never be true is banned outright rather than left as a
    consequence the model has to derive."""
    act_api._hand_over(task, AD)
    note = brain_notes.drain()[0]
    assert "NÓMBRALO EN ESTE TURNO" in note
    assert "no hay resultados" in note and "sigues buscando sin más" in note
    assert note.count("EN ESTE TURNO") == 1


def test_re_extracting_the_same_page_is_not_a_new_finding(task):
    """A worker that scrapes the same list twice must not push the same note twice — noise in this mailbox costs
    the next turn's attention, and the mailbox is bounded (20)."""
    act_api._hand_over(task, HOTEL)
    brain_notes.drain()
    act_api._hand_over(task, HOTEL)
    assert brain_notes.drain() == []


def test_but_a_DIFFERENT_extraction_does_get_through(task):
    """Sensitivity, and the actual sequence of the case: the ad first, the hotel afterwards. Deduplicating by
    task instead of by content would have swallowed the only good result of the round."""
    act_api._hand_over(task, AD)
    brain_notes.drain()
    act_api._hand_over(task, HOTEL)
    assert "Exe Sevilla Macarena" in "".join(brain_notes.drain())


def test_an_empty_extraction_says_nothing(task):
    """Zero results is the extractor's business, not news for the operator."""
    act_api._hand_over(task, [])
    assert brain_notes.drain() == []
    assert (tasks.get(task) or {}).get("results") in (None, {})


def test_an_unknown_task_never_raises():
    """Best-effort like every other seam in this bridge: `act` must not fail because the card is gone."""
    act_api._hand_over("no-existe-esta-tarea", HOTEL)


def test_a_conclusion_already_written_is_not_wiped(task):
    """`_finalize_web` writes the conclusion at the end; this runs DURING the task and must not blank it."""
    tasks.set_results(task, {"conclusion": "lo que dijo el worker", "items": []})
    act_api._hand_over(task, HOTEL)
    res = (tasks.get(task) or {}).get("results") or {}
    assert res.get("conclusion") == "lo que dijo el worker" and res.get("items") == HOTEL


def test_the_extract_branch_ACTUALLY_calls_it():
    """The half that makes it behaviour. V2-186's lesson, and V2-215's: a helper nobody calls is a fix that dies
    one line short of its reader."""
    import inspect
    src = inspect.getsource(act_api.navegador_act)
    assert '_hand_over(task_id, items)' in src
    assert src.index('if action == "extract"') < src.index('_hand_over(task_id, items)')
