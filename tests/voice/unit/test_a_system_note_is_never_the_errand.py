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


# The V2-049 forced escalation left `nucleo.py` on 2026-09-01 (architecture ratchet). Now that it is a module
# it can be DRIVEN instead of grepped — which is the better guard: a source scan cannot tell a live call from
# a mention of itself, and this file has been bitten by exactly that.
def _drive(reply, *, op_text, did_act=False, pending=None, web=True):
    """Run the real backstop with fakes, and report what it emitted and what it escalated."""
    from voice.engine.llm.providers import promise_backstop as pb
    events, launched = [], []
    pb.run(reply, did_act=did_act, op_text=op_text, prev_pending=pending or [],
           emit=lambda *a, **k: events.append((a[1] if len(a) > 1 else "", k.get("text", ""))),
           escalate=lambda req, context=None: launched.append(req),
           similar_pending=lambda *_a: False)
    return [e[0] for e in events], launched


def test_the_forced_escalation_never_launches_the_glued_note():
    """The incident: a real promise about a real web errand escalates the OPERATOR's words, never the note."""
    labels, launched = _drive("Voy a por ello ahora mismo.",
                              op_text="entra en Wallapop y bórrame los anuncios viejos")
    assert launched == ["entra en Wallapop y bórrame los anuncios viejos"]
    assert any("promesa sin acción" in l for l in labels)


def test_a_clarifying_question_launches_nothing_at_all():
    labels, launched = _drive("¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro.",
                              op_text="entra en Wallapop y bórrame los anuncios viejos")
    assert launched == [], "a question asking for the missing datum bought a Brain Worker and a browser"
    assert any("pregunta aclaratoria" in l for l in labels), "and the fact stays measurable"
    assert not any("promesa sin acción" in l for l in labels)


def test_a_turn_that_already_acted_is_left_alone():
    assert _drive("Voy a por ello.", op_text="entra en Wallapop y borra algo", did_act=True) == ([], [])


def test_the_other_three_work_making_seams_read_the_operator_too():
    """Same door, more handles: the irreversible-order backstop, the escalation's own fallback goal, and the
    same-turn create-widget backstop. Checked by their unique text, not by a region — a region wide enough to
    hold all three also holds lines that legitimately read the turn."""
    src = NUCLEO.read_text(encoding="utf-8")
    for good, bad in (("is_dangerous(_op_text)", "is_dangerous(text)"),
                      ('req = escalate_req["v"] or _op_text', 'req = escalate_req["v"] or text'),
                      ("create_widget_request(_op_text)", "create_widget_request(text)")):
        assert good in src, f"`{good}` is the seam that manufactures work — it must read the operator's words"
        assert bad not in src, f"`{bad}` is the bug coming back"


# ── the note is a BLOCK, and a question is not a promise (2026-09-01, session 651cd038) ───────────────────
"""The plumber came back, through the other door.

The operator pressed Reset, restarted his browser and asked for catamaran prices. Two browsers opened. The
second card was titled «Cita en Valls» — a city name from a medical-appointment errand of weeks earlier, taken
from a late recall's `[SISTEMA]` note. Three things had to be true at once, and every one of them was:

  1. The V2-049 promise backstop (the FORCED escalation) still read the note-prefixed turn text. Yesterday's
     fix converted its sibling block and left this one; the source guard only watched the sibling.
  2. `strip_system_notes` — the single door every escalation passes through — strips only the LINES that start
     with the prefix, and the late-recall note announces itself on line one and then LISTS what it recovered.
     Its body survived, and with it the errand's name.
  3. The reply that triggered it was «¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro.»
     — the agent asking for the datum it needs, which is the correct behaviour. The «te lo miro» read as an
     unkept promise.

Measured over every firing of that gate in the operator's own sessions (2026-08-17 → 2026-09-01): of ten, THREE
were a clarifying question and only one ever escalated — the one above.
"""

NOTE_MULTILINE = (
    "[SISTEMA] La memoria durable llegó tarde para la pregunta «Es el primer turno. Salúdame en 1-2 frases» "
    "del turno anterior. Esto es lo que tenía: Puede que venga a cuento (de tu memoria):\n"
    "· La ciudad se llama Valls (pronunciado 'Valch').\n"
    "· El operador prefiere que se use solo su nombre de pila; si piden un apellido, que se invente uno.\n"
    "· Usa solo mi nombre, Vale, pues mira, quiero cita para mí, ¿vale? Búscame el traumatólogo, y creo que e")
ASKED_FRAGMENT = "A ver, quiero ver cuáles son los precios"


def test_a_multiline_note_does_not_leak_its_body_through_the_single_door():
    """Stripping only line one is WORSE than not stripping: what is left has lost the `[SISTEMA]` marker that
    would let anyone downstream recognise it, so it reads as something the operator said."""
    from nucleo.flash import escalate
    got = escalate.strip_system_notes(NOTE_MULTILINE + "\n\n" + ASKED_FRAGMENT)
    assert got == ASKED_FRAGMENT, "the note's body became the operator's request — that is «Cita en Valls»"
    assert "Valls" not in got and "·" not in got


def test_only_notes_still_yields_nothing_to_do():
    from nucleo.flash import escalate
    assert escalate.strip_system_notes(NOTE_MULTILINE) == ""


def test_a_turn_with_no_notes_is_untouched():
    """The common case must not change: a plain turn keeps every one of its lines."""
    from nucleo.flash import escalate
    plain = "búscame un hotel en Soria\n\npara el jueves"
    assert escalate.strip_system_notes(plain) == plain


def test_a_note_never_carries_a_blank_line_of_its_own():
    """That blank line is the ONLY mark of where the notes end and the operator begins. A worker's summary is
    free text, and one push away from splitting itself in two and handing its tail over as a request."""
    from voice import brain_notes
    brain_notes.drain()
    brain_notes.push("[SISTEMA] Brain worker · Tarea completada: encontré esto\n\ny esto de aquí abajo")
    note, = brain_notes.drain()
    assert "\n\n" not in note
    assert "y esto de aquí abajo" in note, "the fix must not truncate the note, only its blank lines"


ASKS_FOR_A_DETAIL = [
    "¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro.",
    "Zaragoza a la ciudad de... me has dejado la frase a la mitad, Ricard — ¿a qué ciudad quieres ir?",
    "Perdona, Ricard: me falta saber los dos puntos exactos para poder calcular el trayecto.",
    "Which model are you looking for?",
]
REALLY_PROMISES = [
    "¡Claro! Me pongo a buscar un digestólogo en Soria. Dame un momento y te enseño lo que encuentre.",
    "Voy a mirarlo, Ricardo.",
    "Ahora mismo te la enseño. Estoy aún con la búsqueda, que va un poco lenta.",
    "Me pongo con ello. ¿Te aviso cuando lo tenga?",
]


@pytest.mark.parametrize("reply", ASKS_FOR_A_DETAIL)
def test_a_clarifying_question_is_not_a_broken_promise(reply):
    from nucleo.flash import router
    assert router.asks_for_missing_detail(reply)


@pytest.mark.parametrize("reply", REALLY_PROMISES)
def test_a_real_promise_leaves_the_backstop_armed(reply):
    """The counterweight, and it is the half that keeps V2-049 alive: «dame un momento» is a promise wearing an
    imperative, and «¿te aviso cuando lo tenga?» is a courtesy question. Neither asks for a datum."""
    from nucleo.flash import router
    assert not router.asks_for_missing_detail(reply)


def test_the_accent_is_the_signal_and_is_not_normalized_away():
    """In Spanish the interrogative carries the accent and the conjunction does not. Strip accents and
    «te aviso cuando lo tenga» becomes a request for information."""
    from nucleo.flash import router
    assert router.asks_for_missing_detail("¿Cuándo lo quieres?")
    assert not router.asks_for_missing_detail("Te lo digo cuando lo tenga.")


def test_both_promise_gates_consult_it_and_so_does_the_probe():
    """Wired in BOTH channels: this class of defect survives by diverging between voice and probe."""
    src = NUCLEO.read_text(encoding="utf-8")
    assert "asks_for_missing_detail(spoken_text)" in src, \
        "the no-tool backstop in the turn body has to consult it"
    pb = NUCLEO.parent / "promise_backstop.py"
    assert "asks_for_missing_detail(spoken_text)" in pb.read_text(encoding="utf-8"), \
        "and so does the forced escalation, now that it lives in its own module"
    probe = NUCLEO.parents[4] / "nucleo" / "flash" / "probe.py"
    assert "asks_for_missing_detail(spoken)" in probe.read_text(encoding="utf-8")


def test_use_case_the_ghost_errand_of_2026_09_01():
    """The incident, replayed through the real guards with the strings the engine actually saw.

    The trigger is the third assertion: with the note glued on, `looks_like_web_task` said True — that is what
    turned a clarifying question into a Brain Worker with a browser."""
    from nucleo.flash import router
    glued = NOTE_MULTILINE + "\n\n" + ASKED_FRAGMENT
    reply = "¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro."

    op = router.operator_words(ASKED_FRAGMENT, glued)
    assert op == ASKED_FRAGMENT
    assert router.looks_like_web_task(glued), "premise: the glued note is what made this look like a web task"
    assert not router.looks_like_web_task(op), "the operator asked for prices of nothing yet — no errand here"
    assert router.asks_for_missing_detail(reply), "and the gate closes one step earlier still"


def test_the_call_site_still_matches_the_module_it_calls():
    """The extraction's own risk, and the one a unit test of `run()` cannot see: `_run_inner` calls it with
    seven keywords, and a signature that stops matching would raise at the END of every voice turn — after
    the reply streamed, so the operator would hear an answer and then the turn would blow up."""
    import ast
    import inspect

    from voice.engine.llm.providers import promise_backstop as pb

    tree = ast.parse(NUCLEO.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "run" and getattr(n.func.value, "id", "") == "_promise_backstop"]
    assert len(calls) == 1, "the backstop is called from exactly one place — the end of the turn"
    call, = calls
    sig = inspect.signature(pb.run)
    keywords = {k.arg for k in call.keywords}
    required = {n for n, p in sig.parameters.items()
                if p.default is inspect.Parameter.empty and p.kind is not p.VAR_KEYWORD} - {"spoken_text"}
    assert not (required - keywords), f"the call site never passes {required - keywords}"
    assert not (keywords - set(sig.parameters)), f"the call site passes {keywords - set(sig.parameters)}"

    # …and every name it reads is bound in that function, so this cannot raise NameError either.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_inner")
    bound = {t.id for n in ast.walk(fn) for t in ast.walk(n)
             if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
    bound |= {a.arg for a in fn.args.args} | {"emit", "_similar_pending"}
    used = {k.value.id for k in call.keywords if isinstance(k.value, ast.Name)}
    assert not (used - bound), f"the call site reads unbound names: {used - bound}"
