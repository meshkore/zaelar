"""A `[SISTEMA]` note is CONTEXT for the turn. It can never become the thing to go and do.

Measured live, operator session c480413b (2026-08-31). He asked for an appointment with a traumatologist in
Soria through Sanitas. What appeared on his screen, in the widget titles and out loud was a PLUMBER:

    «Oye, el proceso "· [tarea web] un fontanero que pueda ven" pregunta: …»

The chain, event by event:
  1. Turn one's recall did not close inside the 800 ms budget — `memory | recall sin entregar`.
  2. It finished afterwards, and `recall_budget.py` salvaged it as a note for the NEXT turn:
     `[SISTEMA] La memoria durable llegó tarde … Esto es lo que tenía: · [tarea web] un fontanero…`.
  3. `nucleo.py` glues pending notes to the front of the turn: `text = notes + "\\n\\n" + text`. The line right
     above it captures `operator_text` BEFORE that, and says why — the notes are «NUNCA como parte de lo que el
     operador pidió».
  4. The promise-backstop then read `text`, not `operator_text`. A Brain Worker was born with that memory line
     as its goal, racing the real errand for nine minutes: two browser tabs, two results cards, two workers.

So the fix was already sitting in the file as a variable. What was missing was using it at the seam that turns
a promise into WORK — the one place where reading the wrong string does not just confuse an answer, it spends
money and fills the screen.
"""
import pytest

from nucleo.flash import router

NOTE = ("[SISTEMA] La memoria durable llegó tarde para la pregunta «Hola, ¿estás ahí?» del turno anterior. "
        "Esto es lo que tenía: Puede que venga a cuento (de tu memoria):\n"
        "· [tarea web] un fontanero que pueda venir hoy → Me he quedado sin cuota en el proveedor.")
ASKED = "Necesito concertar una cita en un traumatólogo en Soria."


def test_the_operators_words_win_over_the_glued_note():
    assert router.operator_words(ASKED, NOTE + "\n\n" + ASKED) == ASKED


def test_the_plumber_cannot_survive_into_the_goal():
    """The concrete regression: whatever comes out of this must not carry the old errand's words."""
    got = router.operator_words(ASKED, NOTE + "\n\n" + ASKED)
    assert "fontanero" not in got.lower(), \
        "a memory line about an old errand became a live Brain Worker's goal — nine minutes and two workers"
    assert "[SISTEMA]" not in got


def test_without_an_operator_text_it_behaves_exactly_as_before():
    """Fail-safe: a caller that never separated the two must not change behaviour. Making this an error would
    turn a note-only turn into a crash on the voice hot path, which is worse than the bug."""
    assert router.operator_words("", "lo que sea que llegara") == "lo que sea que llegara"
    assert router.operator_words(None, "algo") == "algo"


def test_whitespace_only_operator_text_is_not_an_answer():
    assert router.operator_words("   ", "el turno entero") == "el turno entero"


# ── the seam itself: the backstops must read the operator, not the turn ───────────────────────────────────
from pathlib import Path

NUCLEO = Path(__file__).resolve().parents[3] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _backstop_block() -> str:
    src = NUCLEO.read_text(encoding="utf-8")
    i = src.find('_no_tool = (not acted["widget"]')
    assert i > 0, "the backstop block moved: this guard would be watching nothing"
    j = src.find("BACKSTOP DETERMINISTA de CIERRE", i)
    assert j > i, "the end of the backstop block moved: this guard would be watching nothing"
    return "\n".join(l for l in src[i:j].splitlines() if not l.strip().startswith("#"))


def test_no_backstop_reads_the_note_prefixed_turn_text():
    """Deliberately crude (this repo's convention for guarding a seam by text): every backstop decision in that
    block has to go through the operator's own words. A bare `text` there is the bug coming back."""
    block = _backstop_block()
    assert "_op_text = _router.operator_words(operator_text, text)" in block, (
        "`_op_text` has to come from `operator_words(operator_text, …)`. Assigning it `text` keeps every call "
        "site below looking correct while feeding them the note-prefixed turn again — the bug, renamed")
    for bad in ("looks_like_create_widget(text)", "looks_like_escalate_task(text)", "looks_like_show_strict(text)",
                'escalate_req["v"] = _win_goal or text', '{"query": text,', "_identify(text)",
                "escalate_goal_from_window(brain._window, text)"):
        assert bad not in block, \
            f"`{bad}` reads the turn WITH the system notes glued on — that is how the plumber became an errand"
