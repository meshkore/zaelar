"""nucleo/flash/escalation_guard.py — the two non-reasoner failures that must become an errand.

Extracted from the voice provider on 2026-09-11 paying the architecture ratchet (V2-677 pushed
`nucleo.py` over its ceiling, and the table calls for extracting a concern rather than raising a number).
The extraction also SINGLE-SOURCES a decision the probe was mirroring by hand — V2-252's parallel-
implementation rule, applied instead of maintained.

GUARD MARKETPLACE → NAVEGAR + MODIFICAR-WIDGET → GENERADOR (V2-057, 2026-07-21): two RELIABLE failure
modes of the fast non-reasoning model. (a) a NAMED marketplace plus an intent to search demands entering
and driving the catalogue (a worker), not one datum from `web_search`. (b) changing a widget's CODE or
appearance (colour, column, style) is the generator's work, not a data-op and not an «I can't». In both,
when the turn neither escalated nor touched another tool, it escalates.
"""
from __future__ import annotations

ESCALATE_INSTRUCTIONS = (
    "Decide whether this turn needs a background worker. The assistant already does these ON THE SPOT, "
    "with its own cards, in one step: play or pause music, play videos, show images, charts and maps, "
    "send or read a message, read or change the calendar, read a document already on screen, recall what "
    "it remembers, open or close a card. Those are handle_inline even when phrased as orders. A worker costs "
    "minutes and money: escalate only real background work — researching or comparing things on the web, "
    "navigating websites, WRITING a new document or summary, building a widget, a multi-step errand — and "
    "PUTTING TOGETHER a collection of several items chosen for him (a list of things picked to fit what he "
    "describes), even when it will end up in one of its own cards. Adding ONE named item to a list is inline."
)

ESCALATE_CHOICE = {
    "handle_inline": "Answerable or doable right now with the assistant's own cards and memory: a fragment, "
                     "a reaction, chatter, a question, or a one-step order to music, video, images, charts, "
                     "maps, messages, the calendar or a card",
    "escalate": "The turn commissions real background work: web research or comparison, navigation, "
                "writing a new document or summary, building, putting together a collection of several items "
                "chosen to fit what he describes, or any multi-step errand",
}

# V2-776 (2026-09-27) — the question used to say «handle_inline ONLY for what is clearly not an errand … when in
# doubt, escalate». Measured live on the demo's phrases it escalated 11 of 11 one-step orders (music, Telegram,
# the calendar, a stock chart) with confidence up to 0.99, and each one became a 50-60 s worker.


def judge_escalation_from_brief(brief) -> str:
    """The escalate verdict READ from the turn's brief — no socket, no thread, no wait (V2-726 F2).

    The blocking re-ask it replaced (`judge_escalation`, deleted in refactor2710-07) sat inside
    the voice provider's `async def`: up to 900 ms of frozen event loop, on the loop STT, TTS and
    barge-in share, and measured the gate that times out most often (28% of its calls). The brief is
    fired when the turn starts and read here after the model has answered, which is 2-4 s later.

    Returns "escalate" for everything that is not a confident `handle_inline` — an unsure verdict, a
    brief still in flight, a failed or disabled one: today's path, unchanged.
    """
    from nucleo.turn import brief as _tb
    choice, _info = _tb.read(brief, _tb.ESCALATE_KEY, "escalate")
    return "handle_inline" if choice == "handle_inline" else "escalate"


def word_tables(router, brief, *texts, emit=None) -> str:
    """What the WORD TABLES (`looks_like_escalate_task`, `looks_like_create_widget`, the window lookback) may do
    with an empty promise: "go" (they matched and nothing refuses), "" (no match: the lookback may still try) or
    "refused" — a confident `handle_inline` the brief already paid for (CRIT-K1, V2-802 T-07).

    V2-753 installed this in `promise_backstop` and the post-stream promise branch kept escalating on the words
    alone: «Ayer te pedí hacer una reserva en un restaurante… ¿todo eso ya debería estar en tu memoria?» — a
    question about our own past, brief `handle_inline` 1.00 — met «reserva» in the table, and a web worker went
    to look for restaurants. Grammar proposes; the verdict decides. An unsure, missing or in-flight verdict keeps
    today's path, because a missed errand is still worse than a wasted question. Both channels ask this."""
    hit = any(router.looks_like_create_widget(t) or router.looks_like_escalate_task(t) for t in texts if t)
    if not keeps_it_inline(brief, str(texts[0]) if texts else "", emit=emit if hit else None, by="word_table"):
        return "go" if hit else ""
    return "refused"


def keeps_it_inline(brief, text: str = "", *, emit=None, by: str = "") -> bool:
    """The turn's SURE `handle_inline`: the ONE reader every route that would open a worker for this turn asks
    (T-19 R6c). Demo pass 7, INIT: «Remember these… even when they are not on the calendar» — `handle_inline` 0.96,
    the model called nothing, and the order-over-a-card lane sent it to a worker that wrote meetings into the agenda.
    With `emit`, a refusal is said once (measurable, never silent)."""
    if judge_escalation_from_brief(brief) != "handle_inline":
        return False
    if emit:
        emit("brain", "🚫 promesa→escalada ANULADA por el veredicto (handle_inline)", text=str(text)[:120],
             role="system", extra={"cat": "flash", "kind_diag": "promise_inline", "by": by})
    return True


def escalation_text(operator_text: str, turn_text: str) -> str:
    """The errand to escalate, or "" — read from the OPERATOR'S WORDS, never the composed turn.

    V2-677. `turn_text` carries the `[SISTEMA]` notes glued on by `brain_notes.compose_turn`, and MEASURED
    live (session e896f596, 23:16:36) that was enough to spawn a real `claude_code` worker off the KICKOFF
    GREETING: the three words that satisfied `looks_like_modify_widget` were «añade» (from our own «añade
    en una frase lo que sigue»), «fondo» (from «La tarea de fondo…») and «panel» (from «Lo tienes en el
    panel de estado») — not one of them the operator's. That worker ran for fifty seconds and came back
    with a Spanish greeting into an English session.

    A high-precision guard reading the wrong text is a coin flip, and this one spends money. `operator_
    words` exists for exactly this, and its own docstring tells the same story one backstop over: a late
    recall note became the errand, and an appointment with a traumatologist came back as a PLUMBER
    (V2-534). The rule is not about any one note — **a system note is context; it can never be the thing
    to go and do.**
    """
    from . import router as _router
    words = _router.operator_words(operator_text, turn_text)
    if _router.looks_like_marketplace_nav(words) or _router.looks_like_modify_widget(words):
        return words
    return ""


def is_a_fragment(operator_text: str, *, brief=None, last_reply: str = "") -> bool:
    """`router_guards.too_thin_to_commission`, minus the one shape the brief already tells us about.

    THE DEFECT (live session 092569ab, 2026-09-21, the very first turn). The engine offered to deal
    with an AliExpress email. The operator said «Sí.» — and the ghost-worker guard, which annuls a
    1-3 word turn with no directive in it, annulled the commission as «un fragmento, no un encargo».
    Nothing happened, and twelve seconds later he said «pues nada, olvídalo».

    A confirmation is SHORT BY NATURE. «Sí», «vale», «hazlo» carry no directive verb because the
    directive was in OUR sentence, not in his — so a guard that reads only his words is structurally
    unable to tell a dictation tail from a yes. That is why it needs the fact it does not have, and
    the fact is already bought: the turn brief's `request_type` has a verdict spelled «the user
    answers a question WE just asked», and on this very turn it returned `answer` at **1.00**.

    Both halves are required. The verdict says the turn is an answer; `answered_an_offer` says there
    was a question to answer — the same pairing `canvas_license.offer_of_media` documents, and for
    the same reason: a «yes» is an answer only where there was a question. Without a brief this is
    `too_thin_to_commission` verbatim, which is today's path.

    A go-ahead to an offer with no question mark («…I can dig into that if you want» → «do it») is not read here
    from the words: the offered work is a pending ROW, and `resume_turn.before_fragment_guard` resolves the turn
    against those rows (a verdict over their labels and our line) before this guard runs (V2-831 T-07).
    """
    from . import router_guards as _rg
    if not _rg.too_thin_to_commission(operator_text):
        return False
    from nucleo.flash import prior_line as _prior
    if _prior.answers_our_question(brief, last_reply):
        return False                      # he is answering us: the errand is ours, not his to repeat
    return True


def drop_if_fragment(escalate_req: dict, *, operator_text: str, brief=None,
                     last_reply: str = "", emit=None) -> bool:
    """Annul a commission the turn could not have made, and say so. `True` when it was annulled.

    The guard's whole body, in the module that owns the decision rather than in the voice provider —
    the architecture ratchet's standing answer to «this block grew» (V2-726 A7, V2-740, V2-741). The
    provider keeps the call; both channels get the same rule, `is_a_fragment`'s exception included.

    Never raises: a guard that throws would take the turn with it, and the safe side of this one is
    leaving the commission exactly where it is.
    """
    try:
        from nucleo.turn import brief as _tb
        # V2-820 T-06 — the turn's words as the verdict read them: a «vale» after his own cut request is not the
        # whole of what the model was answering, and the commission came from the cut words.
        if not escalate_req.get("v") or not is_a_fragment(_tb.judged_text(brief, operator_text), brief=brief,
                                                          last_reply=last_reply):
            return False
        if emit:
            emit("brain", "🧭 escalada anulada — el turno es un fragmento, no un encargo",
                 text=f"{(operator_text or '')[:80]} → {(escalate_req.get('v') or '')[:80]}",
                 role="system", extra={"cat": "flash"})
        escalate_req["v"] = None
        escalate_req["more"] = []
        return True
    except Exception:  # noqa: BLE001
        return False


# ── V2-726 A3 · a commission is RESOLVED, never silently cleared ─────────────────────────────────
#: What became of a commission the model proposed. Every one of them ends as exactly one of these,
#: and the disposition is emitted — a commission that simply disappears is the engine's oldest
#: failure («it says it will and it doesn't»), and until now an annulled one left one log line.
DELEGATED = "delegated"                  # a worker was launched: the task row of V2-728 owns it
HANDLED_INLINE = "handled_inline"        # the turn produced a concrete result of its own
PROMISED = "promised"                    # the reply committed to it: it may NOT be annulled
UNRESOLVED = "unresolved"                # nothing acted, nothing promised: kept, which escalates
ANSWERED = "answered"                    # a question the state answers: the caller composes it (`second_pass`)


def a_question_the_state_answers(brief) -> bool:
    """The verdict reads the turn as a QUESTION that wants WORDS and needs no worker — all three sure (2026-10-21).

    Manual session 374a2ae2: «did I send you a long prompt yesterday?» → the brief said question · tell ·
    handle_inline, the model called `escalate_to_slowbrain` anyway and replied «let me get that», and a worker spent
    four minutes failing to find what the turn's own record held. The reply PROMISED, so the gate below kept the
    commission. A question is not an errand: what it asks is answered from the turn's own state — any question,
    in any language, about anything the state holds — and the promise is honoured by that answer, not by a worker.
    Read from the verdict, never from the words.

    …and only when what he gets back is SAID (2026-10-27). «Give me the carbonara recipe» read question · tell ·
    handle_inline as well, with `errand_surface = informe`: a written thing to read. Annulled as «answered», it was
    composed from the STATE alone — «I don't have a carbonara recipe stored here, want me to search the web?» — and
    a search the turn never needed ran for minutes. A turn whose surface is something to LOOK at (a document, a
    list, one item, pictures, a new card) is not answered by the state: it goes on to the rung that writes it."""
    from nucleo import surfaces as _sf
    from nucleo.turn import brief as _tb
    return (_tb.read(brief, _tb.REQUEST_KEY, "")[0] == "question"
            and _tb.read(brief, _tb.WORDS_KEY, "")[0] == "tell"
            and _tb.read(brief, _tb.ESCALATE_KEY, "")[0] == "handle_inline"
            and _sf.normalize(_tb.read(brief, _sf.SURFACE_KEY, "")[0])
            not in (_sf.LIST, _sf.ITEM, _sf.DOC, _sf.IMAGES, _sf.WIDGET))


def covered_by_live_work(commission: str, *, anything_running: bool) -> bool:
    """Is a task ALREADY RUNNING **this very** commission? Not «is any task running».

    THE DEFECT (live session 092569ab, 2026-09-21). The operator asked for ten restaurants near the
    Torre del Oro while an unrelated Apollo-11 worker was still going. The gate read
    `anything_running=True`, annulled the commission as `handled_inline / worker-running`, and the
    model had just said «voy a lanzar de una la búsqueda de los diez restaurantes ahora mismo».
    Nobody ever searched for a restaurant. The errand did not fail — **it was never born**, and the
    only trace was one log line saying a worker was running, which was true and irrelevant.

    `anything_running` answers «is the engine busy». The question this gate needs is «is what he
    just asked for already being done», and the engine has answered that one since V2-507: the
    dispatch dedup, which compares content words against the goals of the LIVE errands and carries
    its evidence with its verdict. It is reused here rather than re-derived, which is the whole of
    V2-252's parallel-implementation rule: a second copy of a similarity rule drifts, and then two
    gates disagree about whether two sentences are the same errand.

    The `kind` handed over is the neutral one on purpose. `code`/`generic` unlock a shortcut that
    dedups by TARGET WIDGET, and two different errands about the same card are still two errands —
    exactly the over-matching this function exists to stop.
    """
    if not anything_running:
        return False                      # nothing is running: there is nothing to be covered BY
    words = str(commission or "").strip()
    if not words:
        return False
    try:
        from nucleo import dispatch as _dispatch
        dup, _ev = _dispatch.dedup_scan(words, "web")
        return bool(dup)
    except Exception:  # noqa: BLE001 — the gate may never break the turn
        return False


def annulment_verdict(jev_choice: str, *, reply: str, acted: bool,
                      anything_running: bool, commission: str = "", answerable: bool = False, brief=None) -> dict:
    """May a confident `handle_inline` annul this commission? `{annul, disposition, why}`.

    THE DEFECT THIS EXISTS FOR (V2-726 audit, finding 4). The gate ran AFTER the model had answered
    and after speech had usually started, and a confident `handle_inline` cleared `v` and every
    entry of `more`. But a turn that carried an escalation normally REPLIED with a promise — «te lo
    busco», «me pongo con ello» — so annulling it produced the exact shape this engine has spent
    three initiatives closing: a promise the operator heard, with nothing on the board behind it.
    `handle_inline` means «this needs no worker». It does not mean «this is already done».

    So the annulment now needs EVIDENCE, and the evidence is local and deterministic — no second
    model, no reasoner asked to referee, nothing the audit warned against:

      · the brief says the turn owed an ORDER and nothing ran (`reply.owes_an_act`, refactor2710-03: a
        verdict, never our words) → the commission stays. An owed act is a debt.
      · the turn ACTED (a widget op, a data read, a search, a listing) or a worker is already
        running → there IS an inline result, and `handle_inline` is describing it correctly.
      · neither → the commission stays. That is today's path and the safe side of this gate, which
        its own instructions already state: «a missed errand is worse than a wasted question».

    Note the direction: this can only make the gate MORE conservative — it never annuls something
    that survives today. That is why it enforces immediately instead of shadowing. A shadow is for a
    change that can newly DO something; this one only declines to undo.
    """
    if (jev_choice or "") != "handle_inline":
        return {"annul": False, "disposition": DELEGATED, "why": "verdict-keeps-it"}
    if answerable and not acted:
        return {"annul": True, "disposition": ANSWERED, "why": "a-question-the-state-answers"}
    if reply_promises(reply, acted=acted, anything_running=anything_running, brief=brief):
        return {"annul": False, "disposition": PROMISED, "why": "reply-promised"}
    if acted:
        return {"annul": True, "disposition": HANDLED_INLINE, "why": "acted"}
    # V2-741 — a worker running SOMETHING ELSE is not evidence that THIS was handled. See
    # `covered_by_live_work` for the errand that was never born because of the old spelling.
    if covered_by_live_work(commission, anything_running=anything_running):
        return {"annul": True, "disposition": HANDLED_INLINE, "why": "covered-by-live-work"}
    return {"annul": False, "disposition": UNRESOLVED, "why": "no-evidence"}


def reply_promises(reply: str, *, acted: bool = False, anything_running: bool = False, brief=None) -> bool:
    """Is an act owed that nothing covers? The BRIEF decides (refactor2710-03, CRIT-K1): an order at its confidence,
    with nothing run and no worker live — a promise over live work is honest («sigo con ello» while a worker runs).
    `reply` is kept for the callers' signature; what our reply said decides nothing."""
    if acted or anything_running:
        return False                    # the act is covered by real work: nothing is owed
    try:
        from nucleo.turn import reply as _reply
        return _reply.owes_an_act(brief) == "order"
    except Exception:  # noqa: BLE001
        return False


def _the_order_was_carried_out(brief) -> bool:
    """No SURE «escalate» in the brief, and the turn's order is one the verdict is sure of at the operator's bar — so the
    act this turn ran IS the commission (live bench E3, 2026-10-15: `forward` + `escalate_to_slowbrain` with the escalate
    key missing from the brief; the worker was kept and was free to send the same mail again). A sure «escalate» — a
    compound turn that also commissions real work — keeps its worker."""
    from nucleo.flash import direct_action as _da, undecided as _und
    from nucleo.turn import brief as _tb
    _c, info = _tb.read(brief, _tb.ESCALATE_KEY, "")
    if info is not None:
        return False
    wid, action = _da.from_brief(brief)
    return bool(wid and action) and _und.sure_order(brief, wid, action)


def settle_commission(escalate_req: dict, *, brief, operator_text: str, reply: str,
                      acted: bool, anything_running: bool, emit) -> dict:
    """Read the gate, decide the DISPOSITION, record it, and clear only if it was earned.

    The whole of V2-726 A3's gate, in the module that owns the decision rather than in the voice
    provider — which the architecture ratchet lists as a god file, and whose answer to «this block
    grew» is «extract a module, do not raise the ceiling». The provider keeps the one thing that is
    genuinely its own: the turn state it is holding (did anything act, is a worker running).

    Never raises and never annuls on an error: `escalate` is the safe side of this gate, and the
    backstops below it in the turn all already handle a commission that is still there.
    """
    try:
        # V2-726 F2 — READ, never call: `judge_escalation` blocks its thread on urlopen, and the
        # voice path runs on the event loop STT, TTS and barge-in share.
        choice = judge_escalation_from_brief(brief)
        if choice != "handle_inline" and acted and _the_order_was_carried_out(brief):
            choice = "handle_inline"
    except Exception:  # noqa: BLE001
        choice = "escalate"
    try:
        verdict = annulment_verdict(choice, reply=reply, acted=acted,
                                    anything_running=anything_running,
                                    commission=str(escalate_req.get("v") or ""),
                                    answerable=a_question_the_state_answers(brief), brief=brief)
    except Exception:  # noqa: BLE001 — the gate may never break the turn
        verdict = {"annul": False, "disposition": DELEGATED, "why": "verdict-error"}
    try:
        emit("brain", f"🧭 comisión → {verdict['disposition']}",
             text=f"{(operator_text or '')[:80]} → {(escalate_req.get('v') or '')[:80]}",
             role="system",
             extra={"cat": "flash", "by": "jev", "jev": choice,
                    "disposition": verdict["disposition"], "why": verdict["why"],
                    "commissions": 1 + len(escalate_req.get("more") or [])})
    except Exception:  # noqa: BLE001
        pass
    if verdict["annul"]:
        escalate_req["v"] = None
        escalate_req["more"] = []
    return verdict
