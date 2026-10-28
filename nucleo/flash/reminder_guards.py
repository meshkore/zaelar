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
import logging as _logging
import re as _re
import time as _time

# At MODULE level, not inside the function (V2-356's rule, inherited with the code it governs): the
# hidden-coupling ratchet counts function-local imports, and there is no cycle to hide — `nucleo.scheduler`
# imports nothing from `flash`. `safe_reminder_schedule` reads it as a module global, which is how the
# 2026-09-02 split first went wrong: left behind in `router_guards`, it raised NameError inside a guard
# whose own fail-soft `except` swallowed it, and the function silently echoed its input back.
from nucleo import scheduler as _sched

from .text_norm import _content_words, _norm_txt, clause_is_only_a_date
from .reminder_fact import reminder_body, tidy_clause


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
# 2026-10-10 (find-a-future-release-and-remind-me EN): the pattern moved to `reminder_promise`, which adds the EN
# determiners («that reminder»), the CLAIM forms («I've got that reminder set», «te he puesto el aviso»), and the
# negation/question check. The names stay here for every reader that imports them.
from . import reminder_promise as _rp
from . import reminder_year as _ry   # the year the conversation said; a day gone by schedules nothing
from nucleo import notice_today as _nt   # an hour gone today rings soon today, and the reply says when
_log = _logging.getLogger(__name__)
_REMIND_NOUN, _REMIND_DET, _REMIND_VERB_RE = _rp._NOUN_ES, _rp._DET_ES, _rp.PROMISE_RE
def promises_a_dated_reminder(reply: str, operator_text: str = "", window=None) -> str:
    """The reply promises to remind the operator AT A GIVEN TIME → the schedule spec for it, else "".

    Returns the spec rather than a bool so the caller cannot promise what it could not resolve: if the moment is
    not unambiguous the answer is "", and nothing gets scheduled on a guessed date.
    """
    found = _rp.find(reply)          # a promise OR a claim, affirmed (not negated, not asked)
    if not found:
        return ""
    n, m = found
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
    # 2026-10-10: «I'll set that reminder» on an «ok 👍» turn — the day is the one his earlier ask named.
    return (_sched.parse_when(n[m.end():])
            or _asked_reminder_moment(operator_text)
            or _sched.parse_when(operator_text)
            or _asked_moment_in_window(window))
def already_in_agenda(note: dict) -> bool:
    """Is this commitment already written down for that day?

    Lives NEXT TO the write and not inside a decision on purpose: a decision is a pure function
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
    try:                              # V2-769 — a repeating appointment is on every day its rule lands on
        from widgets.agenda import recur as _recur
        _on = _recur.on
    except Exception:  # noqa: BLE001
        def _on(m, d):
            return str(m.get("date") or "") == d
    for m in meetings:
        if not _on(m or {}, str(note.get("date") or "")):
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
def _asked_moment_in_window(window, max_back: int = 6) -> str:
    """The moment his most recent reminder ASK in the window named, read by position — or ""."""
    turns = [str((m or {}).get("content") or "") for m in (window or []) if (m or {}).get("role") == "user"]
    return next((w for w in (_asked_reminder_moment(t) for t in reversed(turns[-max_back:])) if w), "")
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
    return tidy_clause(head)        # V2-781 pair 3: strip(" ,.;:y") cut CHARACTERS («hoy» → «ho»)
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
    if not when:
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
        c = _dt.datetime.strptime(commitment.strip(), "%Y-%m-%d %H:%M") if commitment else None
    except Exception:
        return when
    # 2026-10-14: an instant already gone TODAY is not «already early» — it rings soon today (`notice_today`), the
    # next full hour rather than five minutes, and that move is noted so the reply says the time it rings at.
    if (c is None or w.date() < c.date()) and not (w <= now and w.date() == now.date()):
        return when
    if c is not None and w.date() >= c.date():
        w -= _dt.timedelta(days=7)
    if w <= now:
        n_ts, c_ts = now.timestamp(), (c.timestamp() if c else None)
        return _nt.stamp(_nt.moved(w.timestamp(), _nt.soon(n_ts, before=c_ts), n_ts))
    return w.strftime("%Y-%m-%d %H:%M")


def commitment_moment(operator_text: str, window=None) -> str:
    """When the commitment a notice announces happens («el jueves tengo que…» → Thursday 09:00), or ""."""
    clause = commitment_from_window(window, operator_text) if window else commitment_clause(operator_text)
    # A clause that is nothing but a date states no event, so there is nothing for the notice to precede
    # (see `clause_is_only_a_date`). Passing it on would make `reminder_before` fire the notice at once.
    return "" if clause_is_only_a_date(clause) else (_sched.parse_when(clause) or "")


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
def safe_reminder_schedule(schedule: str, reply: str, operator_text: str = "", window=None) -> str:
    """WHEN the model tag's notice fires — as `_schedule_as_asked` reads it, and then BEFORE the commitment.

    2026-10-14 (`remember-and-remind-deadline`, asked on the Wednesday itself at noon): the model wrote today 09:00,
    the scheduler refused it as past, and the correction below answered «el miércoles» = NEXT Wednesday — after the
    Thursday deadline. A one-off instant now passes through `reminder_before`, the backstop's own rule: never after
    the commitment, and an hour already gone today rings soon today. Two limits keep V2-356's contract: the model's
    OWN future instant stands (it may read the request better than a rule), and a commitment that resolves to today
    («el jueves» said on a Thursday) is ambiguous, so it bounds nothing."""
    spec = _schedule_as_asked(schedule, reply, operator_text, window)
    if not _re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", spec):
        return spec
    if spec == (schedule or "").strip() and _sched.parse_schedule(spec):
        return spec
    try:
        until = commitment_moment(operator_text, window)
        today = _time.strftime("%Y-%m-%d", _time.localtime(_time.time()))
        return reminder_before(spec, until if until[:10] > today else "")
    except Exception:  # noqa: BLE001 — the model's own instant still goes to the scheduler
        _log.warning("reminder deadline check failed", exc_info=True)
        return spec
def _schedule_as_asked(schedule: str, reply: str, operator_text: str = "", window=None) -> str:
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
        # 2026-10-11 — a one-off day the conversation dated WITH a year keeps that year: «September 30th» rolled to
        # 2027 while the search had said «September 30th, 2026». A day gone by stays gone (`create` refuses it).
        once = spec if _re.match(r"\d{4}-\d{2}-\d{2}\b", spec) else ""
        if not once and not _sched.parse_schedule(spec):
            once = _sched.parse_when(spec) or ""
        if once and (fixed := _ry.anchored(once, reply or "", operator_text or "", window)) != once:
            return fixed
        # With the REPLY available, position wins («lo que va después de "te avisaré"»). Without it —the provider
        # path executes the tag while generation is still underway— use the OPERATOR's turn, which is the
        # authority anyway: the operator said «recuérdamelo el miércoles».
        pedido = (promises_a_dated_reminder(reply or "", operator_text or "")
                  if (reply or "").strip() else _asked_reminder_moment(operator_text or ""))
        if not pedido:
            return spec                       # without an unambiguous answer, correct nothing
        pedido = _ry.anchored(pedido, reply or "", operator_text or "", window)   # a past day: `suyo` is None below
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
