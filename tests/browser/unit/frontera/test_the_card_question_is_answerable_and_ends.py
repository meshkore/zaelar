"""V2-605 — a card question the operator can ANSWER, and that ends.

Measured 2026-09-07, session `43b7bf79` (10:58-11:06), read event by event before touching anything. The
operator was watching a Brain Worker drive TheFork and offered to help:

    OPERADOR  o me abres el navegador para que yo lo vea, y te confirme el captcha
    ZAELAR    Te abro el navegador para que lo veas. Tienes 2 abiertas: ¿cuál te enseño, «t1» o «navegador»?
    OPERADOR  Pues uno está vacío y el otro tiene la web del… Así que no creo que sea muy complicado saber
              la que te estoy preguntando.
    ZAELAR    Tienes 2 abiertas: ¿cuál te enseño, «t1» o «navegador»?
    OPERADOR  ¿Eres tonto o qué te pasa?
    ZAELAR    Tienes 2 abiertas: ¿cuál te enseño, «t1» o «navegador»?

Five times, verbatim. THREE faults, each with its own opposite, and all three are established here:

  · **The question named IDS.** `_label` could only title a `results` sheet; every other piece fell through to
    the instance suffix and the base id. The module's own docstring already forbade exactly that — «"¿results::t1
    o results::t2?" is not a question, it is a dump» — so the rule existed and reached one widget. A card is now
    named by WHAT IT SHOWS, asked of the widget that owns it (`data.card_face`).
  · **A blank card was a candidate.** One tab was on thefork.es and the other on `about:blank`. His answer is the
    specification: showing somebody a card with nothing on it is never what they asked for while a sibling has
    content. SHOWING only — `resolve_close` keeps asking, because there the blank card is the cheap one to get
    wrong and the full one is somebody's work.
  · **The question could not end.** `clarify["msg"]` REPLACES the model's reply, so nothing the model wanted to
    say could break the loop, and the anti-repetition nudge fired into a sentence the model does not write. Asked
    once: on a repeat we choose and SAY which — a decision he can correct in one word beats a question he cannot
    escape. Same shape as V2-530, one axis over.
"""
import tempfile

import pytest

from widgets import instances, store
from widgets.navegador import tasks

#: The canvas exactly as it was reported at 11:04:50 (`ui/canvas (instancias)`).
CANVAS = ["mensajeria", "navegador::t1", "results::adb1ee-3", "navegador"]
ASK_HE_GOT = "Tienes 2 abiertas: ¿cuál te enseño, «t1» o «navegador»?"


@pytest.fixture(autouse=True)
def _aislado(monkeypatch):
    """Isolated store, and the browser registry restored — `tasks._tasks` is process-global live state."""
    monkeypatch.setattr(store, "DATA_DIR", tempfile.mkdtemp())
    store._last_hash.clear()
    _saved = dict(tasks._tasks)
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()
    tasks._tasks.update(_saved)
    store._last_hash.clear()


def _tab(tid, url, page_title="", title="Tarea"):
    tasks._tasks[tid] = {"id": tid, "goal": title, "goal_summary": "", "title": title, "url": url,
                         "page_title": page_title, "events": [], "status": "running"}


def _thefork():
    _tab("t1", "https://www.thefork.es/", "Reserva en los mejores restaurantes de España | TheFork")


# ── 1) the incident itself ────────────────────────────────────────────────────────────────────────────────────

def test_the_blank_card_is_not_a_candidate_for_being_shown():
    """His own words: «uno está vacío y el otro tiene la web». There is nothing to ask."""
    _thefork()
    out = instances.resolve_show("navegador", CANVAS,
                                 "o me abres el navegador para que yo lo vea y te confirme el captcha")
    assert out["ask"] == "", f"volvió a preguntar: {out['ask']}"
    assert out["id"] == "navegador::t1"


def test_the_exact_question_he_got_can_no_longer_be_produced():
    _thefork()
    assert instances.resolve_show("navegador", CANVAS, "ábreme el navegador")["ask"] != ASK_HE_GOT


# ── 2) a card is named by what it SHOWS ───────────────────────────────────────────────────────────────────────

def test_a_browser_card_is_named_by_its_site_not_its_id():
    """The HOST, which is how the operator named it himself («el otro tiene la web del Tenedor»). Not the page
    title: that is marketing prose with the site's name LAST, so capping it to a speakable length drops exactly
    the identifying half — found by this test, on the first version of the fix."""
    _thefork()
    assert instances._label("navegador::t1") == "thefork.es"


def test_a_blank_card_is_named_as_blank_not_by_the_pieces_own_name():
    """«Navegador»/«Nuevo navegador» is the PIECE's name: as a card label it distinguishes nothing, which is the
    whole failure. The seeded title must never win here."""
    lab = instances._label("navegador")
    assert lab == instances.BLANK_LABEL
    assert "avegador" not in lab


def test_a_card_label_is_short_enough_to_say_out_loud():
    _tab("t9", "", "Reserva en los mejores restaurantes de España y Portugal al mejor precio", title="")
    assert len(instances._label("navegador::t9")) <= 44


def test_a_piece_that_cannot_describe_its_cards_keeps_the_old_id_fallback():
    """`card_face` is optional. A widget without it must behave exactly as before — never a guessed label."""
    assert instances.card_face("mensajeria") == {}
    assert instances._label("mensajeria::t3") == "t3"


# ── 3) with two REAL cards the question is asked — once ───────────────────────────────────────────────────────

def test_two_cards_with_content_still_ask_and_the_options_are_readable():
    _thefork()
    _tab("t2", "https://www.booking.com/", "Booking.com | Hoteles")
    out = instances.resolve_show("navegador", ["navegador::t1", "navegador::t2"], "enséñame el navegador")
    assert out["ask"] and out["id"] is None
    assert "thefork.es" in out["ask"] and "booking.com" in out["ask"]
    assert "«t1»" not in out["ask"] and "«t2»" not in out["ask"], "volvió a nombrar ids"


def test_the_same_question_is_never_asked_twice():
    _thefork()
    _tab("t2", "https://www.booking.com/", "Booking.com | Hoteles")
    ids = ["navegador::t1", "navegador::t2"]
    first = instances.resolve_show("navegador", ids, "enséñame el navegador")
    again = instances.resolve_show("navegador", ids, "que no, el otro", last_spoken=first["ask"])
    assert again["ask"] == "", "repitió la pregunta que ya había hecho"
    assert again["id"] in ids
    assert again["chose"], "eligió y no dijo cuál"


def test_a_different_previous_sentence_does_not_suppress_a_first_question():
    """The anti-loop must not eat the FIRST ask — that would replace a repeated question with a silent guess."""
    _thefork()
    _tab("t2", "https://www.booking.com/", "Booking.com | Hoteles")
    out = instances.resolve_show("navegador", ["navegador::t1", "navegador::t2"],
                                 "enséñame el navegador", last_spoken="Hecho.")
    assert out["ask"], "se tragó la primera pregunta"


def test_all_blank_cards_still_ask_because_the_ambiguity_is_real():
    """Narrowing only ever helps when it leaves something: two blank tabs are a genuine question."""
    _tab("t1", "about:blank")
    _tab("t2", "about:blank")
    out = instances.resolve_show("navegador", ["navegador::t1", "navegador::t2"], "enséñame el navegador")
    assert out["ask"], "eligió a ciegas entre dos tarjetas en blanco"


# ── 4) CLOSING keeps asking — same input, opposite risk ───────────────────────────────────────────────────────

def test_closing_still_asks_when_one_is_blank_but_now_names_them():
    """Showing a blank card is harmless noise; CLOSING the wrong one destroys somebody's work, so the default
    is the opposite. What closing gains here is a question that can be answered."""
    _thefork()
    out = instances.resolve_close("navegador", ["navegador::t1", "navegador"], "cierra el navegador")
    assert out["ask"], "dejó de preguntar al cerrar"
    assert "thefork.es" in out["ask"] and instances.BLANK_LABEL in out["ask"]


def test_closing_both_is_still_answered_without_a_question():
    """V2-530 stays intact."""
    _thefork()
    out = instances.resolve_close("navegador", ["navegador::t1", "navegador"], "cierra las dos")
    assert out["ask"] == "" and len(out["ids"]) == 2


# ── 5) the SHEET keeps naming itself — the knowledge MOVED, it was not lost ───────────────────────────────────
# `_label` used to hardcode the sheet's title; V2-605 moved that into `widgets/results/data.card_face` so every
# instantiating piece answers the same way. A move is only safe if the destination is measured: the first disarm
# round deleted the sheet's face and every test here stayed GREEN, because none of them opened a sheet.

def _sheet(inst, title="", items=()):
    from widgets.results import data as sheet
    store.save(sheet.sheet_key(inst), {"title": title, "items": list(items)})


def test_a_sheet_is_named_by_the_request_it_shows():
    _sheet("a1", "Fontaneros en el centro de Madrid", [{"title": "x"}])
    _sheet("a2", "Motos de segunda mano", [{"title": "y"}])
    out = instances.resolve_close("results", ["results::a1", "results::a2"], "cierra los resultados")
    assert "Fontaneros en el centro de Madrid" in out["ask"]
    assert "Motos de segunda mano" in out["ask"]


def test_two_untitled_sheets_are_still_told_apart():
    """«Resultados» is `view_data`'s filler, not a name: two of them would ask a question that distinguishes
    nothing. The instance is the only thing guaranteed to differ, so it comes back as the tiebreaker."""
    _sheet("b1", "", [{"title": "x"}])
    _sheet("b2", "", [{"title": "y"}])
    out = instances.resolve_close("results", ["results::b1", "results::b2"], "cierra los resultados")
    assert out["ask"] and "b1" in out["ask"] and "b2" in out["ask"]
    assert "Resultados" not in out["ask"]


def test_an_empty_sheet_is_not_shown_while_a_full_one_is_open():
    """The V2-300 incident with its own vocabulary: the errand's sheet full of rows beside the bare, empty box."""
    _sheet("c1", "Guitarras de segunda mano", [{"title": "x"}])
    _sheet("c2", "")
    out = instances.resolve_show("results", ["results::c1", "results::c2"], "enséñame los resultados")
    assert out["ask"] == "" and out["id"] == "results::c1"


# ── 6) THE THIRD DOOR — the deterministic fallback (V2-605 F2) ────────────────────────────────────────────────
# Found by driving the LIVE engine, not the bench. «Enséñame el navegador» called NO tool and emitted NO tag —
# the model answered «Listo.» and a deterministic backstop produced the show — so it never touched the
# `show_widget` path this pass had already fixed, and opened the BARE card with four on the canvas. The close
# side of that same fallback has consulted the instance since V2-259; the show side never did.

def test_the_fallback_narrows_a_base_to_its_live_card():
    _thefork()
    assert instances.show_id("navegador", CANVAS, "enséñame el navegador") == "navegador::t1"


def test_the_fallback_never_asks_and_falls_back_to_the_base():
    """It has no channel to hold a conversation, so ambiguity keeps the old behaviour rather than going silent."""
    _tab("t1", "https://a.example/", "A")
    _tab("t2", "https://b.example/", "B")
    assert instances.show_id("navegador", ["navegador::t1", "navegador::t2"], "el navegador") == "navegador"


def test_an_unknown_canvas_changes_nothing():
    assert instances.show_id("navegador", [], "el navegador") == "navegador"


def test_the_voice_fallback_show_branch_consults_the_instance():
    """The asymmetry that caused it: close consulted `_close_target`, show emitted the bare id."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/widget_intent.py"
    body = src.read_text(encoding="utf-8").split("def _widget_fallback(", 1)[1].split("\ndef ", 1)[0]
    code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    assert "_close_target(" in code, "el fallback dejó de consultar la instancia al CERRAR"
    assert "_show_target_instance(" in code, "el fallback no consulta la instancia al MOSTRAR"
