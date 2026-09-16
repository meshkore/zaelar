"""V2-710 · Work that has ALREADY RUN is not a new errand, and the auditor has to be able to see that.

## The session

`7a22136c`, 2026-09-16. The operator's own reading of it, unprompted:

> «Lo que me ha parecido más preocupante es que cuando ya habíamos hecho las tareas, él me pregunta si
> quiero continuar con la tarea. Y después, cuando ya hemos terminado todo, descubro que hay un proceso de
> background que también intenta hacer lo mismo. Es como si para hacer una tarea estuvieras lanzando varios
> procesos a la vez para la misma tarea. Eso sí es un problema grave.»

He is describing this, event by event:

    i=562  widget data:clear_range {from: 2026-09-17, to: 2026-09-17}
    i=635  ✅ acción irreversible confirmada
    i=668  zaelar «Everything from tomorrow the seventeenth is now deleted — done.»
    i=762  he     «But but it's okay with me.»                      ← he agrees it is done
    i=777  susurro 👂 fricción detectada — «petición repetida (no atendida)»
    i=782  susurro 🚀 worker_action → escalada
                  «Delete every appointment on Thursday, September 17, 2026 from Richard's real calendar…»
    i=786  task   dedup_miss — «encargo NUEVO: no había ninguna tarea viva contra la que comparar»
    …      five hundred events of a Brain Worker fighting permission gates to empty an empty day…
    i=1086 he     «Why do we have yet a process working in the system?»

## The two holes, and they are one question asked at two places

`dedup_miss` said it in its own words: there was no live task to compare against. There wasn't — **the
work was DONE, and done work is not a live task.** The dedup in `dispatch` compares a request against
`active_sessions()`, and V2-570 already taught it about one kind of finished work (a delivered listing fast
pass, `recent_listing_deliveries`). Nobody taught it about a finished DATA-OP, even though `done_ops`
(V2-707 F6) is exactly that ledger, written in the single mutation funnel and only when the op happened.

And upstream of that, the auditor's diagnosis was wrong for a reason worth fixing rather than working
around: its window carried the conversation, the turn decisions, the event ring and the state — and not the
one fact that settles «was this attended?». `live_blocks.done_ops_lines()` had been putting that in the
FAST brain's prompt since V2-707 F6. Giving one reader of a question the ledger and not the other is how
the two came to disagree about whether the calendar had been emptied.

So: the auditor SEES what ran, and `worker_action` refuses to launch a second worker for it.
"""
from __future__ import annotations

import pytest

from nucleo import asked_count, done_ops
from nucleo.susurro import apply as sapply
from nucleo.susurro import window as swindow

#: The request the auditor actually escalated, verbatim from i=782.
ESCALATED = ("Delete every appointment on Thursday, September 17, 2026 from Richard's real calendar (the "
             "source the agenda widget mirrors), leaving only that day emptied, and then reflect the "
             "change in the agenda widget and memory.")


@pytest.fixture(autouse=True)
def clean_ledger():
    done_ops.reset()
    yield
    done_ops.reset()


# ── 1 · the measured escalation ─────────────────────────────────────────────────────────────────────────

def test_the_worker_that_redid_the_deletion_is_refused():
    assert sapply._already_executed(ESCALATED) is None, "with nothing run yet it must NOT block"
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    ran = sapply._already_executed(ESCALATED)
    assert ran and ran["wid"] == "agenda" and ran["action"] == "clear_range"


def test_it_reads_the_WIDGET_LAYER_verb_set_not_the_irreversibility_classifier():
    """Measured while building this: `danger.is_dangerous(ESCALATED)` is **False**, and correctly so — that
    classifier judges real-world irreversibility (money, commitments, subscriptions), not widget rows. The
    op that ran was stamped destructive by `widgets/contract`, so `contract` has to be the reader that
    agrees with it. Two readers of one question is the defect this whole week has been about."""
    from nucleo import danger
    assert danger.is_dangerous(ESCALATED) is False, \
        "if this ever flips, the reader below can be reconsidered — but not silently"
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    assert sapply._already_executed(ESCALATED) is not None


# ── 2 · what must NOT be swallowed ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("req", [
    "Remove the third video from the youtube list",                       # another widget entirely
    "Find out why the agenda count says eleven when he only sees four",   # no removal verb — a real errand
    "Add the dentist appointment to the agenda for Friday at nine",       # a creation, not a removal
    "Search coches.net for a van under eight thousand euros",
])
def test_a_different_errand_still_escalates(req):
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    assert sapply._already_executed(req) is None, req


def test_a_read_only_op_is_not_a_reason_to_refuse_anything():
    """Only a DESTRUCTIVE op falsifies the “it did not execute” premise. `show_day` changes nothing, so a
    worker asked to delete something is still a worker with a job."""
    done_ops.note("agenda", "show_day", {"day": "hoy"}, n=1, destructive=False)
    assert sapply._already_executed(ESCALATED) is None


def test_the_ledger_window_expires():
    """`done_ops` is a SESSION ledger with a window. An op from an hour ago must not veto today's order."""
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    done_ops._DONE[-1]["at"] -= done_ops.WINDOW_S + 60
    assert sapply._already_executed(ESCALATED) is None


# ── 3 · the auditor can SEE it, which is what stops the wrong diagnosis ─────────────────────────────────

def test_the_audit_window_carries_what_already_ran():
    assert swindow.executed_block() == "", "nothing ran — nothing to say"
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    blk = swindow.executed_block()
    assert "agenda:clear_range" in blk and "11" in blk
    doc = swindow.compose_audit_window(reason="petición repetida (no atendida)", signals=[],
                                       turn_ring=[], event_ring=[])
    assert "YA EJECUTADO SOBRE SUS DATOS" in doc, \
        "the auditor decided «not attended» about work it could not see had happened"


def test_both_readers_of_the_question_use_the_same_ledger():
    """The fast brain's prompt and the auditor's window. A fix wired into one and not the other is
    something this codebase has already paid for five times."""
    from nucleo.flash import live_blocks
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    assert "agenda:clear_range" in "\n".join(live_blocks.done_ops_lines())
    assert "agenda:clear_range" in swindow.executed_block()


# ── 4 · «All thirty one appointments» is thirty-one ─────────────────────────────────────────────────────

def test_the_count_he_said_out_loud():
    """i=800/812/858: «All thirty one appointments… Do not repeat them. Uh, clean them all.» The scan
    matched the UNITS word and reported **1**, so the door answered a correct order with a contradiction:
    «You asked me for 1 and there are 31 there: «New»; «New»; … I'm not touching anything until you tell me
    which ones.» He had just said thirty-one."""
    assert asked_count.named("All thirty one appointments") == 31
    assert asked_count.named("clean them all, all thirty one") == 31
    assert asked_count.named("thirty one appointments") == 31


@pytest.mark.parametrize("text,n", [
    ("treinta y una citas", 31),
    ("borra todas las treinta y una", 31),
    ("veintiuna citas", 21),
    ("todas las treinta citas", 30),
    ("all thirty", 30),
    ("thirty-one appointments", 31),
    ("twenty five items", 25),
])
def test_the_class_in_both_languages(text, n):
    assert asked_count.named(text) == n, text


@pytest.mark.parametrize("text", [
    "the thirty first",            # ← an ORDINAL: the 31st of the month. The first draft answered 30.
    "limpia el treinta y uno",     # ← Spanish says the day of the month exactly like this
    "el treinta y uno de mayo",
    "at thirty",                   # ← a price, a duration, a speed: not a count of things
    "thirty one",                  # ← bare, no frame: could be either, so it counts as neither
    "clean the 17th",
    "the seventeenth",
    "Now on Thursdays, the seventeenth",
])
def test_a_DATE_is_never_read_as_a_count(text):
    """The safety property of this module, and the tens rule had to earn it: reading a date as a count makes
    the door refuse a CORRECT order, which is the same defect pointed the other way. A tens number counts
    only behind a quantifier a day of the month never takes («all thirty one») or in front of its counted
    noun («thirty one appointments»)."""
    assert asked_count.named(text) is None, text


def test_what_V2_707_measured_still_reads_the_same():
    assert asked_count.named("clean the three") == 3
    assert asked_count.named("las cinco") == 5
    assert asked_count.named("both") == 2
    assert asked_count.named("3 appointments") == 3
