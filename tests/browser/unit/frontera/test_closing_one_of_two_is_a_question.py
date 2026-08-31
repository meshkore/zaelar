"""V2-259 F3 — “close the results” with two open is a QUESTION, not a guess.

Literal operator request: “if there are 2 results widgets and the user says ‘close the results’, the command
should generate a question: which of the 2 searches should I close, the car search or the plumber search?”.

This is an ambiguity along a DIFFERENT AXIS from the one already handled by `runtime.identify()`. That one decides WHICH PIECE
(“results” → `results`) and asks when there is no name or alias match (V2-082); this one comes later, with the
piece already clear, and what is unknown is WHICH OF ITS CARDS. It could not exist before: the only instantiated piece
was the browser, and its cards close on their own when the task ends. Since V2-259 the operator has two boxes
in front of them with the same name.

What is being established:

  · with one, closing remains closing — a spurious question on every close would be worse than the bug this
    removes, so uncertainty always falls back to the usual behavior;
  · with two, the question names the ERRANDS and not the ids (“results::t1 or results::t2?” is not a question,
    it is a dump);
  · a question that distinguishes nothing is not a question either: two untitled sheets cannot end up with “which
    one should I close, “Results” or “Results”?”;
  · and the rule lives ONCE, even though this close is emitted from three different places.
"""
import re
from pathlib import Path

import pytest

from widgets import instances, store
from widgets.results import data as sheet

ENGINE = Path(__file__).resolve().parents[4]
NUCLEO = ENGINE / "voice/engine/llm/providers/nucleo.py"


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield
    store._last_hash.clear()


# ── 1) with one, closing is closing ───────────────────────────────────────────────────────────────────────────

def test_one_card_closes_without_asking():
    r = instances.resolve_close("results", ["results::t1"])
    assert r["id"] == "results::t1" and not r["ask"]


def test_none_open_still_closes_like_it_always_did():
    """Closing a card that is no longer there is a harmless no-op, and this was always the behavior: the real
    purpose of that emit is to cancel the spurious escalation, not the card."""
    r = instances.resolve_close("results", [])
    assert r["id"] == "results" and not r["ask"]


def test_another_piece_is_not_ambiguous_just_because_results_has_two():
    r = instances.resolve_close("agenda", ["results::t1", "results::t2", "agenda"])
    assert r["id"] == "agenda" and not r["ask"]


def test_an_instance_named_out_loud_is_not_a_question():
    r = instances.resolve_close("results::t9", ["results::t1", "results::t2"])
    assert r["id"] == "results::t9" and not r["ask"]


# ── 2) with two, ask — naming the errands ─────────────────────────────────────────────────────────────────────

def test_two_cards_ask_which_one():
    sheet.apply_action("present", {"sheet": "t1", "title": "Fontaneros en Madrid centro",
                                   "items": [{"title": "Relatores"}]})
    sheet.apply_action("present", {"sheet": "t2", "title": "Coches de segunda mano",
                                   "items": [{"title": "Ibiza"}]})
    r = instances.resolve_close("results", ["results::t1", "results::t2"])
    assert r["id"] is None, "con dos abiertas, elegir una acierta la mitad de las veces y borra la otra mitad"
    assert "Fontaneros en Madrid centro" in r["ask"] and "Coches de segunda mano" in r["ask"]
    assert "results::" not in r["ask"], "la pregunta nombra los ENCARGOS; un id no es una pregunta"
    assert r["options"] == ["results::t1", "results::t2"]


def test_three_cards_read_as_a_list_and_not_as_a_dump():
    for n, t in enumerate(("Fontaneros", "Coches", "Hoteles"), 1):
        sheet.apply_action("present", {"sheet": f"t{n}", "title": t, "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", [f"results::t{n}" for n in (1, 2, 3)])["ask"]
    assert ask.count("«") == 3 and " o «Hoteles»" in ask


def test_a_question_that_cannot_be_answered_is_not_a_question():
    """Two sheets with no errand behind them are both given the placeholder title “Results”. Asking ““Results” or
    “Results”?” forces the operator to answer something that distinguishes nothing — worse than not asking."""
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    assert "«t1»" in ask and "«t2»" in ask
    assert ask.count("Resultados") == 0


def test_colliding_titles_get_disambiguated_instead_of_repeated():
    for sid in ("t1", "t2"):
        sheet.apply_action("present", {"sheet": sid, "title": "Coches", "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    assert "Coches (t1)" in ask and "Coches (t2)" in ask


# ── 3) the rule lives ONCE ─────────────────────────────────────────────────────────────────────────────────────

def test_every_close_path_goes_through_the_one_decision():
    """`nucleo.py` emits `widget/close` with an id from THREE points (the close≠delete guard, the turn backstop, and
    the canvas fallback). The V2-199 wiring guardrail: a decision that nobody calls only proves that the
    code compiles. The fourth time this week that the rule had been — or was about to be — duplicated."""
    src = NUCLEO.read_text(encoding="utf-8", errors="replace")
    con_id = [ln for ln in src.splitlines()
              if 'emit("widget", "close"' in ln and '"id"' in ln]
    assert len(con_id) >= 3, "cambiaron los puntos de cierre: revisa que TODOS pasen por _close_target"
    for ln in con_id:
        assert '_t["id"]' in ln, f"este cierre no pasa por la decisión compartida: {ln.strip()}"
    assert src.count("def _close_target(") == 1, "la decisión tiene que estar escrita UNA vez"


def test_the_ambiguity_is_answered_by_ASKING_and_not_by_staying_silent():
    """Asking ALSO counts as having acted: if the fallback returned False, the login fallback would take the
    turn as if nobody had done anything — the bug documented by V2-023."""
    src = NUCLEO.read_text(encoding="utf-8", errors="replace")
    i = src.index("def _widget_fallback(")
    cuerpo = src[i:i + 3000]
    assert "ask(_t[\"ask\"])" in cuerpo and re.search(r'ask\(_t\["ask"\]\)\s*\n(.|\n){0,400}?return True', cuerpo), (
        "preguntar tiene que contar como actuar")
    assert 'ask=lambda m: clarify.__setitem__("msg", m)' in src, (
        "el fallback no tiene por dónde preguntar: la pregunta se perdería y el cierre no ocurriría — mudo")


def test_the_raw_instances_are_readable_because_the_state_normalizes_them_away():
    """`memory.state()['open_widgets']` stores the BASES, which is correct for what it does: the brain's state
    speaks about pieces. But this question is about CARDS, and normalization erases exactly that data there —
    the same collapse noted by V2-047 F9 and never closed out."""
    from server import voice_api
    voice_api.canvas_state._last_inst = None
    assert voice_api.open_instances() == [], "sin informe del canvas es «no lo sé», no una ambigüedad inventada"
    voice_api.canvas_state._last_inst = ["results::t1", "results::t2", "agenda"]
    assert instances.instances_of("results", voice_api.open_instances()) == ["results::t1", "results::t2"]


# ── V2-300: the MIRROR — “show it to me” does not open the bare box when the errand sheet is in front either ─
#
# Round 24 of `search-buy-guitar__es` (2026-08-24): the errand sheet (`results::58c1af-1`) OPEN with 20
# rows, the operator asks to see a result, the model shows `results` by itself, and the canvas opens the
# BARE box — “I’ll open it for you, although it is empty for now” with the deliverable beside it. The V2-209
# guard told the truth about the wrong box; what was missing was opening the correct one.

def test_showing_the_base_with_ONE_instance_open_resolves_to_the_instance():
    out = instances.resolve_show("results", ["results::58c1af-1", "agenda"])
    assert out["id"] == "results::58c1af-1" and not out["ask"]


def test_showing_with_TWO_instances_open_asks_naming_the_errands():
    out = instances.resolve_show("results", ["results::t1", "results::t2"])
    assert out["id"] is None and "¿cuál te enseño" in out["ask"]


def test_showing_with_NO_instance_open_keeps_the_base_as_always():
    """Sensitivity: with no errand sheets in front, the base is the only one there and opening it is the usual behavior."""
    out = instances.resolve_show("results", ["agenda"])
    assert out["id"] == "results" and not out["ask"]


def test_a_named_instance_passes_through_untouched():
    out = instances.resolve_show("results::t7", ["results::t1", "results::t7"])
    assert out["id"] == "results::t7" and not out["ask"]


def test_the_show_decision_is_wired_in_BOTH_channels():
    """The decision lives ONCE (`instances.resolve_show`) and both channels call it — the kind of bug that
    survives by diverging between voice and probe (V2-252, three times). It is checked against the source WITHOUT comments:
    two guards in this suite already passed with the call deleted because the comment named it."""
    def _code(p):
        lines = Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(ln for ln in lines if not ln.strip().startswith("#"))

    voz = _code("voice/engine/llm/providers/nucleo.py")
    assert voz.count("def _show_target_instance(") == 1
    assert "_show_target_instance(_rid)" in voz, "la voz no consulta la instancia al mostrar"
    probe = _code("nucleo/flash/probe.py")
    assert "resolve_show(_rid" in probe, "el probe no consulta la instancia al mostrar"
