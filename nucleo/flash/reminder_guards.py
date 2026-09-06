"""nucleo/flash/reminder_guards.py — the guards for a PROMISED reminder, note or agenda entry.

Extracted from `router_guards.py` (2026-09-02, architecture ratchet: 1408 lines over a 1374 ceiling, and the
ratchet's own instruction is to EXTRACT a module rather than raise the number). The seam was not chosen for
size — it was measured. Of the 47 guards in that file these 26 form a closed set: they reference each other
and three shared text helpers, and **nothing that stayed behind uses any of them**, so the dependency runs one
way and no import comes back.

WHAT THEY ALL ANSWER. A small non-reasoning model regularly PROMISES a dated notice in prose —«te lo recuerdo
el miércoles»— and emits no tag, so the cron is never created and the promise is simply a lie the operator
only discovers on Wednesday. Every function here exists because of one such measured incident, and the
comments are the incident history: that is what justifies each guard existing at all, and it travels with the
code rather than staying behind in a file that no longer holds it.

The functions moved BYTE FOR BYTE. This module changed no behaviour: it changed where the behaviour lives.
Every name is re-exported from `router_guards`, so no call site anywhere in the repo needed to change —
the same compatibility contract that file's own docstring describes for the split that created it.
"""
import re as _re
import time as _time

# At MODULE level, not inside the function (V2-356's rule, inherited with the code it governs): the
# hidden-coupling ratchet counts function-local imports, and there is no cycle to hide — `nucleo.scheduler`
# imports nothing from `flash`. `safe_reminder_schedule` reads it as a module global, which is how the
# 2026-09-02 split first went wrong: left behind in `router_guards`, it raised NameError inside a guard
# whose own fail-soft `except` swallowed it, and the function silently echoed its input back.
from nucleo import scheduler as _sched

from .text_norm import _content_words, _norm_txt, clause_is_only_a_date


# PROMISE OF A DATED NOTICE (V2-146). «apúntame que el jueves… y recuérdamelo el miércoles» ended with
# `scheduled_jobs.created` EMPTY: the model promised in prose —«te avisaré el miércoles»— and emitted no tag.
# The cron runner works (V2-134), and the prompt asks explicitly; the backstop was missing.
#
# The boundary separating it from the V2-132/V2-143 family: «te aviso EN CUANTO lo tenga» is a worker finishing,
# not a scheduled notice. This case is distinguished by a resolvable MOMENT — and `scheduler.parse_when` decides
# whether one exists, returning "" for any expression that is not unambiguous.
#
# V2-151: the first shape of this pattern spelled out the ARTICLE («program\\w* el recordatorio») and the run it
# was written for said «te programo UN recordatorio» — one word away, and the backstop never fired, so the turn
# promised an alert with `scheduled_jobs.created` empty all over again. Measured on seven natural phrasings of
# the same promise, five missed. A promise is a VERB plus a reminder NOUN; the determiner in between is noise.
# It is listed explicitly instead of `\\w+` so that a NEGATED promise («no te pongo ningún recordatorio») cannot
# match and schedule the very thing the sentence declined to schedule.
_REMIND_NOUN = r"(?:recordatorio|aviso|alarma|alerta)"
_REMIND_DET = r"(?:un|una|el|la|tu|ese|este|esa|esta)\s+"
_REMIND_VERB_RE = _re.compile(
    r"\b(te\s+aviso|te\s+avisare|te\s+lo\s+recuerdo|te\s+lo\s+recordare|te\s+recuerdo|te\s+recordare|"
    r"dejo\s+puesto\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"dejo\s+programad[oa]\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"(?:program|pon|cre|configur|activ|dej)\w*\s+" + _REMIND_DET + _REMIND_NOUN + r"|"
    r"i'?ll\s+remind\s+you|i\s+will\s+remind\s+you|i'?ll\s+let\s+you\s+know\s+on|"
    r"i'?ll\s+set\s+(?:up\s+)?(?:a|the)\s+reminder|i'?ll\s+put\s+(?:a|the)\s+reminder)\b", _re.I)
def promises_a_dated_reminder(reply: str, operator_text: str = "") -> str:
    """The reply promises to remind the operator AT A GIVEN TIME → the schedule spec for it, else "".

    Returns the spec rather than a bool so the caller cannot promise what it could not resolve: if the moment is
    not unambiguous the answer is "", and nothing gets scheduled on a guessed date.
    """
    n = _norm_txt(reply)
    m = _REMIND_VERB_RE.search(n)
    if not m:
        return ""
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return ""
    # The reminder day is the one that follows the promise. Both halves of this exchange name TWO weekdays
    # («el JUEVES renuevas el seguro… te avisaré el MIÉRCOLES»), and `parse_when` refuses an ambiguous pair on
    # purpose — but here the position disambiguates it: what comes after «te avisaré» is when the notice goes.
    #
    # V2-167, 2026-08-20: that same rule was applied ONLY to the reply, and the operator's sentence — which has
    # the identical shape — was handed to `parse_when` WHOLE, so it refused. Measured on
    # `remember-and-remind-deadline`: «Apúntame que el jueves tengo que renovar el seguro del coche, y
    # recuérdamelo el miércoles» → zaelar answered «Voy a apuntarlo y programarte el aviso», the note half fired
    # and the notice half resolved to nothing. The verdict read "confirmed an action it never performed," and the
    # ambiguity it tripped over is not one a person would perceive: the day belongs to whichever verb it follows.
    # So the operator's own turn gets read positionally too, and only then whole (which is what preserves every
    # case that already worked — one date anywhere still resolves exactly as before).
    return (_sched.parse_when(n[m.end():])
            or _asked_reminder_moment(operator_text)
            or _sched.parse_when(operator_text))
# DATED NOTE (V2-159). Sibling of the notice backstop, for the OTHER half of the same request. The prompt says so
# explicitly —"if the commitment has a date, also add it to the agenda… these are two different things, the entry
# and the notice, and the operator asks for both"— yet the run ended with the cron set and NO appointment: «Te apunto la
# renovación del seguro del coche para el jueves» with no data-op behind it.
_NOTE_VERB_RE = _re.compile(
    r"\b(te\s+(?:lo\s+|la\s+)?apunto|apunto|te\s+(?:lo\s+|la\s+)?anoto|anoto|"
    r"queda\s+(?:apuntad|anotad)[oa]|lo\s+apunto|lo\s+anoto|"
    r"(?:anado|pongo|meto)\w*\s+(?:a|en)\s+tu\s+agenda|i'?ll\s+note\s+(?:it|that)\s+down)\b", _re.I)
# Where the date STARTS within the sentence — used both to cut the title before it and avoid dragging it into the
# appointment text.
_DATE_LEAD_RE = _re.compile(
    r"\s*,?\s*\b(?:para\s+el|para|este|esta|el|on|the)?\s*\b("
    r"lunes|martes|miercoles|jueves|viernes|sabado|domingo|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"manana|tomorrow|dia\s+\d{1,2})\b", _re.I)
def dated_note_backstop(reply: str, operator_text: str = "", window=None) -> dict | None:
    """The reply promises to WRITE DOWN a dated commitment → the `add_meeting` payload for it, else None.

    V2-159, measured: the reminder half now works (one cron, right Wednesday, right prompt — V2-151/V2-153) and
    the run still failed because the OTHER half never happened. The case demands both: the commitment REGISTERED
    and the notice scheduled. zaelar said «Te apunto la renovación del seguro del coche para el jueves» and the
    mechanism showed no agenda data-op at all.

    Two details this shares with its sibling, and one it does not:
      · the moment is resolved by `scheduler.parse_when`, so an expression that is not unambiguous schedules
        nothing — a note on a guessed day is the same class of harm as an alert on one;
      · the tail is CUT at the reminder promise before resolving. One sentence carries BOTH days («…para el
        JUEVES y te programo un recordatorio para el MIÉRCOLES») and `parse_when` refuses a pair on purpose;
        position is what tells them apart, exactly as in `promises_a_dated_reminder`.
      · unlike the alert, the title matters: an agenda entry saying «el jueves» is not an entry. It comes from
        the words between the promise verb and the date, falling back to the operator's own request.
    """
    n = _norm_txt(reply)
    m = _NOTE_VERB_RE.search(n)
    if m:
        # STILL ASKING IS NOT SETTLED, and that rule belongs to BOTH branches. It was written for the one below
        # («a question mark means it is still asking, and nothing gets filed on a date it has not settled») and
        # the promise branch never got it — so a reply that promises AND asks in the same breath filed an entry
        # built out of its own question. Reproduced from round 12 of `remember-and-remind-deadline`: «Perfecto,
        # lo anoto. ¿A qué hora del jueves te viene bien la renovación?» put a meeting in the agenda titled
        # «¿a que hora del».
        #
        # Waiting costs one turn and nothing else: this backstop is re-evaluated every turn, so the entry lands
        # as soon as the reply stops asking — measured in the same reproduction, it lands on the turn where the
        # date is finally settled, with the right title. Filing early costs a wrong entry that nobody will go
        # and delete.
        if "?" in (reply or ""):
            return None
        tail = n[m.end():]
        cut = _REMIND_VERB_RE.search(tail)
        if cut:
            tail = tail[:cut.start()]
    else:
        # V2-167 — the reply-verb trigger alone is a treadmill. This run's model said «la cita ESTÁ EN TU AGENDA
        # para el jueves», which asserts the state instead of promising the act, so V2-159's list missed it and
        # the agenda stayed empty for the second run running. What does NOT change between runs is what the
        # OPERATOR asked, so that is what the obligation is read from; the reply is then only consulted for
        # whether the agent backed out — a question mark means it is still asking, and nothing gets filed on a
        # date it has not settled.
        # V2-176: the request to write it down does not EXPIRE because the operator needed another turn to get
        # the date right. Measured: «Apúntalo» was in turn 3, turn 4 only corrected the day, and the agenda stayed
    # empty (`n_after: 1`, only the notice) while zaelar said "I've added it to your agenda."
        if not note_asked_in_window(window, operator_text) or "?" in (reply or ""):
            return None
        clause = commitment_from_window(window, operator_text) if window else commitment_clause(operator_text)
        tail = _norm_txt(strip_note_lead(clause))
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return None
    when = _sched.parse_when(tail)
    if not when:
        return None
    lead = _DATE_LEAD_RE.search(tail)
    # The date can come BEFORE what it dates («el jueves tengo que renovar el seguro») or after it («la
    # renovación del seguro el jueves»). Taking only the text in front of it turned the first shape into an
    # empty title, and an agenda entry with no title is not an entry.
    if lead:
        title = (tail[:lead.start()] or tail[lead.end():]).strip(" ,.;:")
    else:
        title = tail.strip(" ,.;:")
    for _lead_in in ("que ", "tengo que ", "he de ", "debo "):
        if title.startswith(_lead_in):
            title = title[len(_lead_in):]
    if len(title) < 4:
        title = (operator_text or "").strip()[:120]
    return {"title": title[:120], "date": when.split(" ")[0]} if title else None
def already_in_agenda(note: dict) -> bool:
    """Is this commitment already written down for that day?

    Lives NEXT TO the write and not inside `dated_note_backstop` on purpose: that function is a pure decision
    over two strings and a clock, which is why it can be tested against a literal transcript. Reading a global
    store from inside it made nine of its own tests depend on the order the previous ones ran in — the same
    coupling this fix exists to remove, one layer down.

    V2-194, measured in the sandbox of the 2026-08-20 02:34 run: the agenda came out with the SAME commitment
    twice on the same date — «Renovar seguro del coche» and «Renovar el seguro del coche», 2026-08-27. One is
    the model's own data-op and the other this backstop, fired on a later turn.

    The sibling backstop has had this since V2-153 (it refuses to schedule a notice for an instant that already
    has one); the note half never got it, and its gate — «only if THIS turn did not already do the data-op» —
    cannot see a data-op from a PREVIOUS turn. A duplicate alert is a defect the operator hears twice; a
    duplicate agenda entry is one he SEES twice, which is worse because it stays there.

    Compared on the DAY plus the content words of the title, not on the exact string: the two measured entries
    differ by one article, and a comparison that an article defeats is not a comparison. Fail-open — if the
    agenda cannot be read, backing the promise beats dropping it.
    """
    try:
        from widgets import store as _store
        meetings = (_store.load("agenda") or {}).get("meetings") or []
    except Exception:
        return False
    mine = _content_words(str(note.get("title") or ""))
    if not mine:
        return False
    for m in meetings:
        if str((m or {}).get("date") or "") != str(note.get("date") or ""):
            continue
        theirs = _content_words(str((m or {}).get("title") or ""))
        if theirs and len(mine & theirs) >= min(2, len(mine)):
            return True
    return False
# ── V2-167 · a notice arrives BEFORE the event it announces ───────────────────────────────────────────────
#
# The operator's OWN ask, which is not the same vocabulary as the agent's promise (`_REMIND_VERB_RE`, above):
# he says «recuérdamelo», the agent says «te aviso». Both halves live in the same sentence and telling them
# apart is what lets the commitment be read separately from the notice.
# V2-167 round 12 (2026-08-20 12:39) — the operator requested the notice in the SUBJUNCTIVE: «Que me AVISES el
# miércoles 26 por la mañana». This pattern knew only the indicative (`me avisas`), so it missed the request; the
# notice day could not be read positionally, and the whole sentence went to `parse_when` —which sees «jueves 27»
# and «miércoles 26» and rightly refuses— leaving `scheduled_jobs.created` EMPTY while zaelar said «lo dejo
# apuntado y programo el aviso» and finished with «Ya lo tienes todo listo».
#
# This is EXACTLY the failure this module already suffered in V2-151 and documented above: the first pattern
# spelled out one specific variant, while the real run used the neighboring one. Therefore this is broadened by
# MORPHOLOGY (verb stem + ending), not by adding today's phrase to a list: requesting a notice after «que» calls
# for the Spanish subjunctive; it is the natural form, not an unusual variant.
#
# The optional pronoun (`me lo avises` / `me la recuerdes`) is included for the same reason. The stem remains
# paired with its ending instead of a loose `\w*`, so NEGATION («no me avises») does not pull in the pattern.
_REMIND_ASK_RE = _re.compile(
    r"\b(recuerdame\w*|recuerdalo|avisame\w*|"
    r"me\s+(?:lo\s+|la\s+)?(?:avis|recuerd)[ae]s|"
    r"me\s+(?:lo\s+)?mand[ae]s\s+(?:el|un)\s+(?:recordatorio|aviso)|"
    r"remind\s+me|let\s+me\s+know)\b", _re.I)
def _asked_reminder_moment(operator_text: str) -> str:
    """The moment the OPERATOR attached to his own reminder REQUEST, read by position — or "".

    Sibling of the positional read on the reply: «…y recuérdamelo el miércoles» names the notice day right after
    the ask, exactly as «te avisaré el miércoles» does. Reading the sentence whole instead makes a two-weekday
    turn look ambiguous when it is not, which is what left `remember-and-remind-deadline` promising a notice it
    never scheduled.

    Deliberately positional and nothing more: a date BEFORE the ask verb («el martes recuérdame lo del seguro»)
    resolves nothing here and falls through to the whole-sentence read, same as today. Guessing at word order is
    how a backstop starts scheduling things nobody asked for.
    """
    n = _norm_txt(operator_text)
    m = _REMIND_ASK_RE.search(n)
    if not m:
        return ""
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return ""
    return _sched.parse_when(n[m.end():]) or ""
def commitment_clause(operator_text: str) -> str:
    """The part of the operator's turn that states the COMMITMENT, with his reminder request cut off.

    «Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles» carries two days
    and two different obligations. `parse_when` refuses an ambiguous pair on purpose, so position is what tells
    them apart — the same trick `promises_a_dated_reminder` already uses on the reply, applied to the request.
    Returns the ORIGINAL text (not the normalised one) so anything built from it is readable out loud.
    """
    text = operator_text or ""
    n = _norm_txt(text)
    m = _REMIND_ASK_RE.search(n)
    if not m:
        return text.strip()
    end = m.start() if len(n) == len(text) else None
    head = text[:end] if end is not None else n[:m.start()]
    return head.strip(" ,.;:y")
def holding_line(window, lang=None) -> str:
    """The never-mute filler for a turn whose only content is «the task is still running» — one that does NOT
    repeat itself.

    `data_acks` has had this treatment since V2-038, because two «Hecho.» in a row tripped the loop detector.
    The waiting filler never got it, and it is said far more often. Measured on `cheapest-monitor`
    (2026-08-20 01:21): «Vale, dame un momento que lo miro.» FOUR times, word for word, with the operator
    answering «vale, quedo atento» each time; and on `restaurant-tonight-madrid`, five turns of the same. The
    judge marked it grave in both, and it is not the model doing it — the line is emitted here, by us, as a
    backstop for a turn that came back mute.

    Escalates instead of repeating: a fresh variant while there is one, and from the third consecutive wait the
    ONE honest fact available — how long it has been — plus a way out. It never states a step: that is the line
    V2-133 drew ("the fix cannot be to remove them; the filler must avoid claiming a stage"), and
    minutes elapsed are not a step.
    """
    try:
        from voice.engine.core import langs as _langs
        lang = lang or _langs.current_language()
    except Exception:
        return "Sigo con ello."
    lines = tuple(getattr(lang, "holding_lines", ()) or (getattr(lang, "filler_holding", "Sigo con ello."),))
    said = [str((m or {}).get("content") or "").strip()
            for m in (window or []) if (m or {}).get("role") == "assistant"]
    recent = [t for t in said[-3:] if t]
    waits = sum(1 for t in recent if t in lines)
    if waits >= 2:
        mins = _longest_pending_min()
        if mins >= 1:
            waited = str(getattr(lang, "filler_waited", "") or lines[-1]).format(min=mins)
            # In practice the minute count increases, so two consecutive waits are not identical; but if the
            # clock has not advanced a minute, rotate instead of repeating word for word — exactly the defect
            # this fixes, and one that must not be reintroduced through the back door.
            if not recent or waited != recent[-1]:
                return waited
    for line in lines:                      # exhaust the variants BEFORE reusing any of them
        if line not in recent:
            return line
    for line in lines:                      # and if all have already been said, at least not the immediately previous one
        if not recent or line != recent[-1]:
            return line
    return lines[-1]
def _longest_pending_min() -> int:
    """Minutes of the longest-running background task, or 0 when that cannot be read. A FACT, not a step."""
    try:
        from nucleo import dispatch as _d
        return max((int(t.get("secs") or 0) for t in _d.pending_summaries()), default=0) // 60
    except Exception:
        return 0
def commitment_from_window(window, current_text: str = "", max_back: int = 6) -> str:
    """The clause that says WHAT the commitment is, which is not always in the turn that fixes its DATE.

    Same shape of failure `escalate_goal_from_window` already fixed for escalation (V2-132), measured here on
    `remember-and-remind-deadline`, run of 2026-08-20 01:01. The operator states the obligation once and then
    spends two turns correcting the date; by the turn that finally settles it, the subject is gone:

        t1  «Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles»
        t3  «El jueves de esta semana tengo que renovar el seguro del coche. Apúntalo y recuérdamelo…»
        t4  «Sí, perdona, me he liado con las fechas. Me refiero al jueves que viene, 27. Recuérdamelo…»

    Reading t4 alone, `commitment_clause` returns «Sí, perdona, me he liado con las fechas. Me refiero al
    jueves que viene, 27» — and that went in as the reminder's own text, so the job that fires on Wednesday
    reads the operator his own apology back. The judge called it "a useless scheduled notice," which is exactly
    right.

    The rule: the SUBJECT is what he asked for the FIRST time, the DATE is whatever this turn settles on. It
    only looks back when an earlier turn also asked for a reminder or a note — that is what makes this turn a
    CONTINUATION of that request rather than a new one, and it is the guard that keeps a genuinely new errand
    later in the same conversation from inheriting an old subject.

    Known edge, stated rather than hidden: a SECOND reminder about something else, asked in a conversation that
    already had one, will pick up the first subject if this turn names nothing. Telling those apart needs the
    turn to be understood and not matched, which is V2-075's ground (a model judges meaning) and wants its own
    measurement — not a list of apology phrases, which is the treadmill V2-151 already paid for.
    """
    current = commitment_clause(current_text) if current_text else ""
    turns = [str((m or {}).get("content") or "").strip()
             for m in (window or []) if (m or {}).get("role") == "user"]
    turns = [t for t in turns if t][-max_back:]
    asked_before = [t for t in turns[:-1] if _REMIND_ASK_RE.search(_norm_txt(t))
                    or _NOTE_ASK_RE.search(_norm_txt(t))]
    if not asked_before:
        return current
    first = commitment_clause(asked_before[0])
    return first or current
def note_asked_in_window(window, current_text: str = "", max_back: int = 6) -> bool:
    """Did the operator ask for this to be written down — in THIS turn or in an earlier one?

    The other half of the same run: the agenda entry never happened (`n_after: 1`, only the reminder job)
    because the «apúntalo» was in turn 3 and the turn that settled the date was turn 4. An obligation does not
    expire because the operator needed another turn to get the date right.
    """
    if current_text and _NOTE_ASK_RE.search(_norm_txt(current_text)):
        return True
    turns = [str((m or {}).get("content") or "") for m in (window or []) if (m or {}).get("role") == "user"]
    return any(_NOTE_ASK_RE.search(_norm_txt(t)) for t in turns[-max_back:] if t)
# The operator's own «write this down» ask. Sibling of `_REMIND_ASK_RE`, and the counterpart to the agent-side
# `_NOTE_VERB_RE`: the obligation is defined by what HE asked for, which is far more stable than how the model
# happens to word its confirmation — V2-159 matched «te apunto», the next run said «la cita está en tu agenda»,
# and the backstop went quiet. Chasing the model's phrasing is the treadmill V2-151 already paid for.
_NOTE_ASK_RE = _re.compile(
    r"\b(apuntame|apuntalo|apunta\s+que|anotame|anotalo|anota\s+que|"
    r"me\s+(?:lo\s+)?apuntas|ponme\s+(?:en|a)\s+(?:la|mi)\s+agenda|"
    r"note\s+(?:this|that)\s+down|put\s+(?:this|that)\s+in\s+my\s+calendar)\b", _re.I)
def strip_note_lead(text: str) -> str:
    """`text` without the operator's leading «apúntame que…» — what remains is the commitment itself.

    Shared by the agenda title and the reminder prompt so the two cannot disagree about where the commitment
    starts; both were getting «apúntame que» as the thing to file or announce.
    """
    body = (text or "").strip()
    n = _norm_txt(body)
    m = _NOTE_ASK_RE.search(n)
    if not m or m.start() != 0:
        return body
    body = (body[m.end():] if len(n) == len(body) else n[m.end():]).strip(" ,.;:")
    for lead_in in ("que ", "tengo que ", "he de ", "debo "):
        if body.lower().startswith(lead_in):
            return body[len(lead_in):]
    return body
_PROMPT_S = 300          # how soon a reminder fires when the day the operator named has already gone by
def reminder_before(when: str, commitment: str, now=None) -> str:
    """`when` corrected so the notice lands BEFORE the thing it reminds of. Pure; `now` injectable.

    V2-167, measured on `remember-and-remind-deadline`: «Apúntame que el JUEVES… y recuérdamelo el MIÉRCOLES»,
    asked ON a Wednesday. `parse_when("el miercoles")` answers the COMING Wednesday — correct in isolation, and
    the reason it is wrong here is not the parser: it is that a reminder has exactly one constraint the parser
    cannot know about, which is that it must fall before the event. The job went in for 2026-08-26, six days
    after the Thursday it was reminding about.

    So the correction lives here, where both dates are in hand, and NOT in `scheduler.parse_when` — a shared
    date parser with no notion of what it is dating would be the wrong place to teach this.

    Rules, in order: already earlier → untouched; not earlier → the previous occurrence of that same weekday;
    that one already past → fire PROMPTLY, because the day he named is today (or gone) and reminding him now is
    the useful reading of what he asked. Never the silent useless date.
    """
    if not when or not commitment:
        return when
    import datetime as _dt
    if now is None:
        # ONE clock. Every date around this function comes from `scheduler.parse_when`, which reads
        # `scheduler.time.time()`; taking «now» from `datetime.now()` instead meant the correction was computed
        # against a different clock than the dates it was correcting. Invisible in production and lethal in a
        # test: pinning the scheduler's clock moved the inputs and left this one on the wall clock, so the
        # "fire promptly" branch answered with the REAL time and the assertions drifted by hours.
        try:
            from nucleo import scheduler as _sched_clock
            now = _dt.datetime.fromtimestamp(_sched_clock.time.time())
        except Exception:
            now = _dt.datetime.now()
    try:
        w = _dt.datetime.strptime(when.strip(), "%Y-%m-%d %H:%M")
        c = _dt.datetime.strptime(commitment.strip(), "%Y-%m-%d %H:%M")
    except Exception:
        return when
    if w.date() < c.date():
        return when
    w -= _dt.timedelta(days=7)
    if w <= now:
        return (now + _dt.timedelta(seconds=_PROMPT_S)).strftime("%Y-%m-%d %H:%M")
    return w.strftime("%Y-%m-%d %H:%M")
def dated_reminder_backstop(reply: str, operator_text: str = "", window=None) -> dict | None:
    """The whole backstop decision in ONE place: what to schedule when the model promised a notice in prose.

    Both channels — `nucleo/flash/probe.py` and the voice provider — carried their own copy of this (resolve the
    moment, then build the tag), and V2-153 is what a divergence of that shape costs: the run scheduled the
    reminder TWICE, once per turn that promised it, because neither copy looked at what was already scheduled.
    Measured against the real scheduler, two `create()` calls with the same spec both return ok and leave two
    live jobs; nothing downstream deduplicates them.

    Returns the tag payload, or None when there is nothing to add — either no resolvable moment, or that moment
    is already covered. Skipping on an existing job at the same instant is the conservative side on purpose: a
    backstop exists for the turn the model forgot, and a second alert for something the operator asked once is a
    defect he SEES, while the model's own `cron.create` tag is not gated by this and can still schedule freely.
    """
    when = promises_a_dated_reminder(reply, operator_text)
    if not when:
        return None
    # V2-167 · (1) the notice must land BEFORE the thing it announces, and (2) what fires must be the REMINDER,
    # not the request that produced it. The measured job carried the operator's raw turn as its prompt, so on
    # firing the agent would have been asked to SCHEDULE the reminder all over again — the "WHAT gets lost"
    # this case has been dragging since V2-134, finally visible in the field that causes it.
    # V2-176: the WHAT may have been said three turns earlier while this turn only fixes the DATE. Without a
    # window it behaves exactly as before, so no existing caller changes behavior.
    clause = commitment_from_window(window, operator_text) if window else commitment_clause(operator_text)
    try:
        from nucleo import scheduler as _sched
    except Exception:
        return {"schedule": when, "prompt": _reminder_prompt(clause, operator_text), "name": "aviso"}
    # A clause that is nothing but a date states no event, so there is nothing for the notice to precede
    # (see `clause_is_only_a_date`). Passing it on would make `reminder_before` fire the notice at once.
    clause_when = "" if clause_is_only_a_date(clause) else (_sched.parse_when(clause) or "")
    when = reminder_before(when, clause_when)
    if not when:
        return None
    try:
        jobs = list(_sched.list_jobs(active_only=True))
    except Exception:
        jobs = []     # cannot read the schedule → still better to back the promise than to drop it
    for job in jobs:
        if str(job.get("schedule") or "").strip() == when:
            return None
    # V2-153 deduplicated on the exact INSTANT, and that stopped being enough once the instant can be corrected
    # (above): the turn that CARRIES the commitment gets a corrected moment, the one that merely reaffirms it
    # («gracias, así no se me pasa») has no commitment to correct against and would keep the uncorrected one —
    # two different instants for one request, which is exactly the double alert V2-153 exists to prevent. A turn
    # that neither dates a commitment nor ASKS for anything adds no new obligation, so a live notice covers it —
    # while «recuérdame lo del taller», which also carries no date, is a new request and still gets its own.
    asked_now = bool(_REMIND_ASK_RE.search(_norm_txt(operator_text)) or _NOTE_ASK_RE.search(_norm_txt(operator_text)))
    if not clause_now_or_ask(clause_when, asked_now) and any(str(j.get("name") or "") == "aviso" for j in jobs):
        return None
    return {"schedule": when, "prompt": _reminder_prompt(clause, operator_text), "name": "aviso"}
def clause_now_or_ask(clause_when: str, asked_now: bool) -> bool:
    """Does THIS turn create a new obligation? Only if it dates a commitment or asks for something."""
    return bool(clause_when) or bool(asked_now)
def _reminder_prompt(clause: str, operator_text: str) -> str:
    """What the agent is handed when the job fires: an instruction to NOTIFY, carrying the commitment.

    The lead-in («apúntame que…») is stripped because the cron's reader is the agent at a later moment: leaving
    it in asks it to file something, which is precisely the loop this fixes.
    """
    body = strip_note_lead(clause or operator_text or "")
    return f"AVISA al operador, es el recordatorio que te pidió: {body}"[:300]
# ── WHAT THE CRON HANDS BACK TO THE AGENT (V2-214) ────────────────────────────────────────────────────────────
# `_reminder_prompt` composes a safe instruction, and only the BACKSTOP goes through it. When the model emits the
# `cron.create` tag itself, its `prompt` is whatever it wrote — and measured on `remember-and-remind-deadline`
# (2026-08-20 15:49) what it wrote was the operator's own sentence: «el jueves tengo que renovar el seguro del
# coche». The job exists, fires on the right day, and hands the agent a first-person obligation, which reads as
# «file this», not «tell him». So the alert is created and its CONTENT is broken — the judge called it exactly
# that, and it is the loop `_reminder_prompt`'s own docstring already warned about, reached by the other door.
#
# NARROW: only a FIRST-PERSON obligation is rewritten. A cron the operator set up deliberately («cada lunes dame
# el resumen») is already an instruction to the agent, and wrapping it would break a feature to fix a defect.
_FIRST_PERSON_DUTY_RE = _re.compile(
    r"\b(tengo\s+que|he\s+de|debo|me\s+toca|tengo\s+pendiente|"
    r"i\s+have\s+to|i\s+need\s+to|i\s+must|i\s+should)\b", _re.I)
# Already addressed TO the agent: leave it exactly as it is.
_AGENT_IMPERATIVE_RE = _re.compile(
    r"^\s*(avisa|av[ií]same|recu[eé]rda|recuerdame|dime|d[ií]|notif[ií]|remind|tell|notify|let\s+me\s+know)",
    _re.I)
def safe_reminder_schedule(schedule: str, reply: str, operator_text: str = "") -> str:
    """WHEN the model tag's notice fires — corrected if it says TODAY while the conversation requested another day.

    Sibling of `safe_reminder_prompt`, for the other field of the same tag and for the same reason: V2-214
    protected the `prompt` because "the backstop already composed the safe form, while the model's tag came in raw
    through the other door," but left `schedule` entering just as raw.

    Measured in `remember-and-remind-deadline` (2026-08-27): the operator said «el jueves tengo que renovar el
    seguro… recuérdamelo el miércoles»; the turn prompt included the dated list of upcoming days —«wednesday
    2026-09-02»— yet the job had `schedule "2026-08-27 08:08"`: **TODAY, five minutes after the conversation**,
    six days before the event. A notice that fires on the next turn is noise, not a reminder; and a misdated
    notice is not noticed until the day it fails to ring (V2-121).

    Neither parser nor backstop failed — both resolve «el miércoles» to `2026-09-02 09:00`, as verified. The model
    wrote the date despite having the correct one in front of it, and this is where code answers that rather than
    more prompting: when correct behavior is deterministic, code guarantees it (V2-305).

    THE SCOPE IS DELIBERATELY NARROW because the evidence is one case: correction occurs only when **both** are
    true — the tag fires TODAY, and the deterministic resolver has an UNAMBIGUOUS answer on another day. A future
    date is left untouched even if it differs from the resolver's belief: the model may understand the request
    better than a rule, and `parse_when` already stays silent on ambiguity. What cannot be right is «ahora mismo»
    when the person named a day.
    """
    spec = (schedule or "").strip()
    if not spec:
        return spec
    try:
        # With the REPLY available, position wins («lo que va después de "te avisaré"»). Without it —the provider
        # path executes the tag while generation is still underway— use the OPERATOR's turn, which is the
        # authority anyway: the operator said «recuérdamelo el miércoles».
        pedido = (promises_a_dated_reminder(reply or "", operator_text or "")
                  if (reply or "").strip() else _asked_reminder_moment(operator_text or ""))
        if not pedido:
            return spec                       # without an unambiguous answer, correct nothing
        # NORMALIZE first: `scheduler.create` understands only MACHINE forms, so a spoken expression that does
        # resolve («el próximo miércoles por la tarde») is translated here — as the worker path already does
        # (`worker_api`, chaining both parsers); omitting this left the notice uncreated.
        mio = _sched.parse_schedule(spec)
        if not mio:
            _hablado = _sched.parse_when(spec) or ""
            if _hablado and _sched.parse_schedule(_hablado):
                spec, mio = _hablado, _sched.parse_schedule(_hablado)
        suyo = _sched.parse_schedule(pedido)
        if not suyo:
            return spec
        if not mio:
            # The model's date does NOT parse, or has passed (`parse_schedule` rejects the past). Without a
            # correction no job is created and the notice does not exist, so the resolver competes with nothing.
            return pedido
        if str(mio.get("type") or "") != "once":
            # A RECURRING schedule («every 30m», «0 9 * * 3») naturally fires today; that is not the defect:
            # the model specified a cadence, not a date. Correcting it would turn a weekly notice into a one-off.
            return spec
        # ONE CLOCK. `localtime()` without an argument reads the system clock underneath and does NOT pass through
        # `time.time()`, so this function read two clocks: one to parse the date and another to decide what today
        # is. They coincide in production, changing nothing; what breaks is MEASUREMENT — on 2026-08-28 its two
        # tests failed at midnight, having passed until then by calendar coincidence rather than a frozen clock.
        # Passing the instant makes it measurable from one place.
        hoy = _time.strftime("%Y-%m-%d", _time.localtime(_time.time()))
        if _time.strftime("%Y-%m-%d", _time.localtime(mio.get("next_run") or 0)) != hoy:
            return spec                       # does not fire today: not the measured defect
        if _time.strftime("%Y-%m-%d", _time.localtime(suyo.get("next_run") or 0)) == hoy:
            return spec                       # the conversation ALSO requested today: the model was right
        return pedido
    except Exception:  # noqa: BLE001
        return spec
def safe_reminder_prompt(prompt: str) -> str:
    """What the agent is handed when this job fires. Returns `prompt` untouched unless it is the OPERATOR's own
    words about their own obligation, in which case it is wrapped into an instruction to NOTIFY.

    Lives here, next to `_reminder_prompt`, so both doors into the scheduler say the same thing — the backstop
    already did and the model's own tag did not.
    """
    p = (prompt or "").strip()
    if not p or _AGENT_IMPERATIVE_RE.search(p) or not _FIRST_PERSON_DUTY_RE.search(p):
        return p
    return _reminder_prompt(p, p)


def mute_line(window, lang=None) -> str:
    """The never-mute filler for a turn that came back EMPTY with no background work to report — and one that
    does NOT repeat itself, and does not blame the operator (V2-603).

    Sibling of `holding_line`, built for the other branch of the same backstop. That one got anti-repetition in
    V2-189 after «Vale, dame un momento que lo miro.» was measured four times word for word; this branch kept
    a single hardcoded string and was measured doing exactly the same thing on the operator's own engine
    (2026-09-06, session e1acdcca): «Perdona, ¿me lo repites?» four times in ninety seconds, answered with
    «Pero ¿por qué te lo tengo que repetir?».

    The wording change matters as much as the rotation. The old line asked the operator to repeat himself for a
    turn HE had said perfectly well — the model returned nothing, which is our fault, not his — so from the
    outside the agent looks like it cannot understand plain speech. These lines own it instead. Same rule as
    the sibling: never claim a step, never claim work is happening when none is."""
    try:
        from voice.engine.core import langs as _langs
        lang = lang or _langs.current_language()
    except Exception:
        return "Perdona, se me ha ido. ¿Me lo dices otra vez?"
    lines = tuple(getattr(lang, "mute_lines", ()) or ("Perdona, ¿me lo repites?",))
    said = [str((m or {}).get("content") or "").strip()
            for m in (window or []) if (m or {}).get("role") == "assistant"]
    recent = [t for t in said[-3:] if t]
    for cand in lines:
        if cand not in recent:
            return cand
    # Every variant is already in the last three turns: the operator has been talking into a hole. Say THAT,
    # rather than cycling a fourth apology — the only honest thing left is that this is not working.
    return str(getattr(lang, "mute_stuck", "") or lines[-1])


def mute_backstop(window, lang, has_work: bool) -> str:
    """The WHOLE decision for a turn that came back mute, so the two channels share it instead of mirroring it.

    Background work running → say so. Nothing running → `mute_line`, which rotates and owns the fault. Both
    halves used to be written out at each call site, which is how the pending branch got V2-189's
    anti-repetition and the other one kept a single hardcoded «Perdona, ¿me lo repites?» for a year."""
    if has_work:
        return str(getattr(lang, "filler_still_working", "") or "Sigo con ello.")
    return mute_line(window, lang)
