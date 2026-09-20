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
    "Decide whether this turn needs a background worker. "
    "A worker costs minutes and money: answer handle_inline ONLY for what is clearly not an "
    "errand (a dictation fragment, a spelling, a reaction, chatter, something answerable on "
    "the spot). When in doubt, escalate — a missed errand is worse than a wasted question."
)

ESCALATE_CHOICE = {
    "handle_inline": "The turn needs no background worker: a fragment, a reaction, chatter, "
                     "or something answerable right now",
    "escalate": "The turn commissions real background work: research, navigation, building, "
                "or any multi-step errand",
}


def judge_escalation_from_brief(brief) -> str:
    """The escalate verdict READ from the turn's brief — no socket, no thread, no wait (V2-726 F2).

    `judge_escalation` below does the same job with its own blocking call, and that call sits inside
    the voice provider's `async def`: up to 900 ms of frozen event loop, on the loop STT, TTS and
    barge-in share, and measured the gate that times out most often (28% of its calls). The brief is
    fired when the turn starts and read here after the model has answered, which is 2-4 s later.

    Returns "escalate" for everything that is not a confident `handle_inline` — an unsure verdict, a
    brief still in flight, a failed or disabled one: today's path, unchanged.
    """
    from nucleo.flash import turn_brief as _tb
    choice, _info = _tb.read(brief, _tb.ESCALATE_KEY, "escalate")
    return "handle_inline" if choice == "handle_inline" else "escalate"


def judge_escalation(operator_text: str, *, running_goals: list | None = None,
                     has_workers: bool = False, ask_pending: bool = False,
                     timeout_s: float | None = None) -> str:
    """Jev second opinion on a would-be worker commission (T-jev-escalate): "handle_inline"
    annuls it the way the provider annulment does, anything else keeps today's path.

    The verdict is read over the operator's words plus STATE FACTS — which goals are already
    in flight, whether workers run, whether one is waiting for the operator — the same class
    of input the situational gates already use, never a new word list. Returns "escalate" on
    every non-verdict: unsure, slow, failed, disabled, or an empty turn. Fires ONLY where a
    commission survived the grammar guards, never per turn.

    ⚠️ BLOCKING, and therefore no longer for the voice path (V2-726 F2): the voice provider reads
    `judge_escalation_from_brief` instead. This stays for the probe/text channel and for tests,
    which have no brief to read and no event loop to freeze."""
    from nucleo import jev as _jev
    words = (operator_text or "").strip()
    if not words or not _jev.enabled():
        return "escalate"
    goals = [g for g in (running_goals or []) if str(g or "").strip()]
    context = ("Goals already in flight: "
               + ("; ".join(str(g)[:120] for g in goals[:3]) if goals else "none")
               + f"\nWorkers active now: {'yes' if has_workers else 'no'}"
               + f"\nA worker is waiting for the operator's answer: {'yes' if ask_pending else 'no'}")
    verdict = _jev.choose_sync(
        "escalate_or_inline", words, instructions=ESCALATE_INSTRUCTIONS,
        criteria=ESCALATE_CHOICE, context=context,
        timeout_s=timeout_s, question_id="escalate-gate")
    if not verdict:
        return "escalate"
    choice = str(verdict.get("choice") or "")
    if choice != "handle_inline":
        return "escalate"
    if float(verdict.get("confidence") or 0.0) < _jev.MIN_CONFIDENCE:
        return "escalate"
    return "handle_inline"


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


# ── V2-726 A3 · a commission is RESOLVED, never silently cleared ─────────────────────────────────
#: What became of a commission the model proposed. Every one of them ends as exactly one of these,
#: and the disposition is emitted — a commission that simply disappears is the engine's oldest
#: failure («it says it will and it doesn't»), and until now an annulled one left one log line.
DELEGATED = "delegated"                  # a worker was launched: the task row of V2-728 owns it
HANDLED_INLINE = "handled_inline"        # the turn produced a concrete result of its own
PROMISED = "promised"                    # the reply committed to it: it may NOT be annulled
UNRESOLVED = "unresolved"                # nothing acted, nothing promised: kept, which escalates


def annulment_verdict(jev_choice: str, *, reply: str, acted: bool,
                      anything_running: bool) -> dict:
    """May a confident `handle_inline` annul this commission? `{annul, disposition, why}`.

    THE DEFECT THIS EXISTS FOR (V2-726 audit, finding 4). The gate ran AFTER the model had answered
    and after speech had usually started, and a confident `handle_inline` cleared `v` and every
    entry of `more`. But a turn that carried an escalation normally REPLIED with a promise — «te lo
    busco», «me pongo con ello» — so annulling it produced the exact shape this engine has spent
    three initiatives closing: a promise the operator heard, with nothing on the board behind it.
    `handle_inline` means «this needs no worker». It does not mean «this is already done».

    So the annulment now needs EVIDENCE, and the evidence is local and deterministic — no second
    model, no reasoner asked to referee, nothing the audit warned against:

      · the reply PROMISED something (`promises_action` / `promises_music` / `looks_like_show_strict`
        over a promise, or `a_promise_left_hanging`) → the commission stays. A promise is a debt.
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
    if reply_promises(reply, acted=acted, anything_running=anything_running):
        return {"annul": False, "disposition": PROMISED, "why": "reply-promised"}
    if acted or anything_running:
        return {"annul": True, "disposition": HANDLED_INLINE,
                "why": "acted" if acted else "worker-running"}
    return {"annul": False, "disposition": UNRESOLVED, "why": "no-evidence"}


def reply_promises(reply: str, *, acted: bool = False, anything_running: bool = False) -> bool:
    """Did OUR reply commit to something that is NOT already covered? The three existing detectors.

    They are reused rather than re-implemented (V2-252's parallel-implementation rule), and each
    already carries the incident that shaped it: `promises_action` (polite/subjunctive turns where
    the model chatted a promise and called no tool), `promises_music` («te pongo algo de rock» with
    no player touched) and `a_promise_left_hanging` («déjame que lo mire» with nothing running).

    ⚠️ COVERED is the load-bearing word, and the engine's own rule, not a new one:
    `a_promise_left_hanging` already exonerates a promise when the turn ACTED or a worker is
    running, because a promise over live work is honest — «sigo con ello» while a worker runs is a
    true statement, not a debt. Passing the real flags through keeps the two gates agreeing instead
    of inventing a stricter local variant.

    ⚠️ And negation is applied HERE to the look-promise regex. `promises_action` runs through
    `unnegated_match` (V2-534 §1); `a_promise_left_hanging` does not, so «no voy a buscarlo, no hace
    falta» reads as a promise to it. Measured while writing this gate's tests. The shared backstop is
    left alone — for ITS purpose a false positive only costs a nudge — and this gate applies the
    engine's existing negation rule to the same pattern rather than editing a detector three other
    consumers depend on.
    """
    r = (reply or "").strip()
    if not r:
        return False
    if acted or anything_running:
        return False                    # the promise is covered by real work: nothing is owed
    try:
        from nucleo.flash import router_guards as _rg
        if _rg.promises_action(r) or _rg.promises_music(r):
            return True
        from nucleo.flash import answer_guards as _ag
        return bool(_rg.unnegated_match(_ag._PROMISE_TO_LOOK_RE, r.lower())) and "?" not in r
    except Exception:  # noqa: BLE001
        return False


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
    except Exception:  # noqa: BLE001
        choice = "escalate"
    try:
        verdict = annulment_verdict(choice, reply=reply, acted=acted,
                                    anything_running=anything_running)
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
