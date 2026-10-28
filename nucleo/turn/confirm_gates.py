"""One «yes» answers ONE question — the precedence between the three confirmation gates.

THREE THINGS CAN BE WAITING for the same word, and they are not variants of each other:

  · the WIDGET gate (`widgets.confirm`) — a deletion or an irreversible data-op is held.
  · the TASK gate (`nucleo.dispatch`, V2-126) — an irreversible errand was stopped before running.
  · the BROWSER gate (`widgets.navegador.tasks`, V2-202) — a click is blocked INSIDE the page, right now.

They can be open at the same time, and a bare «sí» does not say which one it means. So the answer goes to
exactly one, in that order, and the others stay waiting. That is not a style choice: two of the three arm
something irreversible, so an answer counted twice authorises a payment nobody authorised.

WHY THIS IS A MODULE. Both channels had their own copy of the precedence and one of them drifted. In
`voice/engine/llm/providers/nucleo.py` the browser gate was guarded by `had_pending_confirm` — the WIDGET
gate — instead of by whether the TASK gate had just resolved, so with a task and a click both pending a
single spoken «sí» released BOTH. The comment above that very block said «solo si el sí no ha resuelto ya
otra cosa», which is what kept anyone from looking: a comment asserting the invariant, and no test.
`nucleo/flash/probe.py` had it right. Measured 2026-08-24; zero tests covered the precedence in either
channel.

The decision is returned, never acted on: the caller does the talking and the emitting, because those are
the parts that genuinely differ between a channel with a mouth and one without.
"""
from __future__ import annotations

from dataclasses import dataclass

# The order IS the contract. Nearest-to-irreversible first: a held click is executing right now, a stopped
# task is about to, a widget op is the mildest — but the widget gate goes first because it is the one the
# model was told about in this turn's live state (`confirm.pending_line`), so it is what the operator was
# most likely answering.
GATES = ("widget", "task", "browser")


@dataclass
class Answered:
    """Which gate took the answer, and what it returned. `gate == ""` means nobody did."""
    gate: str = ""
    yes: bool = False
    result: object = None

    def __bool__(self) -> bool:
        return bool(self.gate)


def resolve(text: str, *, widget=None, task=None, browser=None) -> Answered:
    """Give the operator's reply to the FIRST gate that is both open and able to read it.

    Each argument is a pair `(is_open, resolve)` or None when that gate does not apply to this caller. Both
    halves are callables so that nothing is asked — or resolved — once an earlier gate has taken the answer:
    the whole point is that the second gate never sees the word.

    A gate that raises is skipped, not fatal. Losing one confirmation is bad; letting an exception in the
    browser gate take down the turn that was resolving a payment is worse.
    """
    for name, pair in (("widget", widget), ("task", task), ("browser", browser)):
        if not pair:
            continue
        is_open, do_resolve = pair
        try:
            if not is_open():
                continue
            got = do_resolve(text)
        except Exception:  # noqa: BLE001
            continue
        if got is None or got is False:
            # Open but the reply was not a yes/no it could read («¿y cuánto cuestan?»). It stays waiting, and
            # the answer does NOT fall through to the next gate: an ambiguous word is not an authorisation.
            return Answered()
        return Answered(gate=name, yes=_is_yes(got), result=got)
    return Answered()


def _is_yes(got) -> bool:
    """Each gate reports its yes/no differently; this is the one place that knows how."""
    if isinstance(got, dict):
        return bool(got.get("ok"))
    if isinstance(got, str):
        return got == "yes"
    return bool(got)


# ── HOW to reach each gate — which is the same everywhere, so it lives here ─────────────────────────────────
#
# The channels differ in the MOUTH (one speaks the acknowledgement, the other returns an action name), never in
# how a gate is asked. Keeping these adapters in the callers is what let the precedence drift in the first
# place, and it costs the caller a lazy import per gate on top.


def _widget_gate(brief=None):
    def _open():
        from widgets import confirm as _c
        return bool(_c.pending())

    def _do(text):
        from widgets import confirm as _c
        return _c.answers_pending(text, brief)      # the verdict on both channels (audit V2-783 P0-3)
    return (_open, _do)


def _task_gate(brief=None):
    def _open():
        from nucleo import dispatch as _d
        return bool(_d.pending_confirm())

    def _do(text):
        from nucleo import dispatch as _d
        from widgets import confirm as _c
        words = operator_words(text)
        named = _named_parked(words)
        p = _d.pending_confirm(named) or {}
        tid = str(p.get("task_id") or "")
        v = task_reply(words, _c.classify_reply(words), str(p.get("question") or ""), brief=brief, parked=tid,
                       names_it=bool(named) and named == tid)
        if named and (v == "yes" or (v is None and not _names_another_errand(words, tid))):
            # He is talking about THIS errand: what he adds travels with the «yes» (`resolve_confirm`), and the clock
            # restarts — an errand he keeps talking about has not been left unanswered (three-tasks-at-once ES,
            # 2026-10-11: the game expired while he was asking for coins in it, and was then reported as never
            # confirmed). A bare yes adds nothing. A sentence that ALSO talks about another errand is not folded
            # in while it waits: the parked errand would then answer to that errand's words — EN 2026-10-11 02:58,
            # «…btw for the monitor it has to be at least 27 inches» folded into the game made the next sentence
            # about the monitors «name» the game, and its «no» cancelled it.
            if not (v and _c.is_plain_answer(words, v)):
                _d.absorb_refinement(tid, words)
        return _d.resolve_confirm(v == "yes", tid) if v else None
    return (_open, _do)


def _names_another_errand(words: str, parked: str) -> bool:
    """Does the sentence name any errand besides the parked one `parked`?"""
    try:
        from nucleo.turn import named_errand as _ne
        return any(e["id"] != parked for e in _ne.named(words))
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"confirm_gates: errands unreadable — {type(e).__name__}: {e}")
        return True


def _named_parked(words: str) -> str:
    """The id of the PARKED errand his words name most, or "". Several errands can wait on him at once, and the
    newest is not necessarily the one he answers: «Sí, móntalo. Y ponle que salte más alto…» is the game's yes,
    whatever was parked after it (three-tasks-at-once ES, 2026-10-11 02:04)."""
    try:
        from nucleo.turn import named_errand as _ne
        parked = [e for e in _ne.known() if e["parked"]]
        top = _ne.strongest(words, parked) if parked else None
        return str(top["id"]) if top else ""
    except Exception as e:  # noqa: BLE001 — unreadable: the most recent ask answers, as before
        from loguru import logger
        logger.debug(f"confirm_gates: parked errands unreadable — {type(e).__name__}: {e}")
        return ""


def operator_words(text: str) -> str:
    """The turn without the `[SISTEMA]` notes glued in front: our notice's «sin tu OK» is not his vote."""
    from nucleo.acts import errand as _esc
    return _esc.strip_system_notes(text) if "[SISTEMA]" in (text or "") else (text or "")


def task_reply(words: str, v: str | None, question: str, *, brief=None, parked: str = "",
               names_it: bool = False) -> str | None:
    """'yes' | 'no' | None — does the operator's turn ANSWER the parked errand's question? (three-tasks-at-once)

    Measured 2026-10-10 (sandbox 20261010-145227-es): with two errands parked, «Vale. Del monitor que no se te vaya
    de presupuesto» built the game and «Y el juego no te olvides, ¿eh? Que son tres, no dos» dropped the report.
    Neither answers anything: this gate counted bare yes/no WORDS, over a text that still carried our own notes
    («sin tu OK», «Si no te he entendido mal»). Now the reading is the widget gate's (`answers_pending`): only the
    operator's words count; a plain yes/no answers at once; a longer sentence answers when the judge, shown THIS
    question, says it does — and with no judge, only when the turn's verdict reads it as an answer. Otherwise it
    stays waiting: an ambiguous sentence is not an authorisation, and the parked errand can still absorb it."""
    from widgets import confirm as _c
    # The answer his reply OPENS with, when the reply names this errand, is his answer to it — whatever clauses
    # follow. «Sí, justo eso, y ponle que salte más alto, que si no no hay quien pase» read as «no» (last word
    # wins) and «yeah go ahead with the game… btw the monitor…» as OTHER (the judge saw the monitor), so both
    # yeses of 2026-10-11 left the game parked and the agent asked again. A «no» keeps its stricter path below.
    if names_it and _c.opening_answer(words) == "yes":
        return "yes"
    if v is None or _c.is_plain_answer(words, v):
        return v
    if parked and _about_another_errand(words, parked):
        return None
    if parked and v == "no" and not names_it:
        # A long «no» that never names the parked errand does not cancel it: «none of those work… no more than
        # $150, keep looking» was about the monitor listings and dropped the parked game (EN 2026-10-11 02:58, the
        # judge read it «no»). Cancelling needs the errand named or a bare «no»; the errand keeps waiting.
        return None
    judged = _c._judge(question, words) if question else None
    if judged is not None:
        return None if judged == "other" else judged
    from nucleo.flash import turn_brief as _tb
    kind, _info = _tb.read(brief, _tb.REQUEST_KEY, "") if brief is not None else ("", None)
    if kind == "answer":
        return v
    # A «yes» that NAMES the parked errand answers it, whatever else the sentence adds (his «build it, and make the
    # jump higher» read as an ORDER, so it was nobody's yes). A «no» keeps needing the judge or the verdict: a «no»
    # beside the errand's name is as often about one of its details as about the errand.
    return v if (v == "yes" and names_it) else None


def _about_another_errand(words: str, parked: str) -> bool:
    """A sentence that names OTHER errands and not the parked one does not answer the parked one's question.

    three-tasks-at-once (EN, 2026-10-10 20:00): the game was parked on «shall I build it?», and «ah no those are
    all too small — the monitor needs to be at least 27 inches… and did you get the jump change in?» CANCELLED it:
    its «no» was about the monitor listings. The game was never built, and every later «did you get the jump in?»
    had no errand to answer about. Bounded on the consequence: such a sentence leaves the errand parked — it can
    still absorb the refinement — and a plain yes/no above is untouched."""
    try:
        from nucleo.turn import named_errand as _ne
        named = _ne.named(words)
        return bool(named) and not any(e["parked"] and e["id"] == parked for e in named)
    except Exception:  # noqa: BLE001
        return False


def _browser_gate():
    # No separate «is it open?»: `answer_from_turn` already decides that with the state it owns. Asking twice
    # would mean two reads of the same thing, and two reads can disagree.
    def _do(text):
        from widgets.navegador import tasks as _t
        return _t.answer_from_turn(text)
    return (lambda: True, _do)


def resolve_all(text: str, *, widget: bool = False, brief=None) -> Answered:
    """The standard resolution: every gate a channel can answer, IN ONE CALL — which is the invariant.

    One call is what makes «the second gate never sees the word» true by construction instead of by the caller
    remembering to guard it. Splitting this back into one call per gate is the defect, whatever goes in between.

    `widget=True` includes the widget gate. Voice handles that one earlier in its turn (it has to speak the
    acknowledgement and return), so by default it is left out rather than resolved twice. `brief` is the turn's
    verdict handle: the task gate reads it when a long reply cannot be judged (`task_reply`).
    """
    return resolve(text,
                   widget=_widget_gate(brief) if widget else None,
                   task=_task_gate(brief) if brief is not None else _task_gate(),
                   browser=_browser_gate())
