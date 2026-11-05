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
one fact that settles «was this attended?». `live_record.done_ops_lines()` had been putting that in the
FAST brain's prompt since V2-707 F6. Giving one reader of a question the ledger and not the other is how
the two came to disagree about whether the calendar had been emptied.

So: the auditor SEES what ran, and `worker_action` refuses to launch a second worker for it.

V2-851 F5: the auditor is gone (a task is born only from his words, through `flow_of.route`), so its
`worker_action` path no longer exists to be refused. What stays is the reader that remains: the fast brain's
prompt carries the ledger of what already ran.
"""
from __future__ import annotations

import pytest

from nucleo import asked_count, done_ops

@pytest.fixture(autouse=True)
def clean_ledger():
    done_ops.reset()
    yield
    done_ops.reset()


# ── 1 · the reader that stays sees what already ran ────────────────────────────────────────────────────

def test_the_fast_brains_prompt_carries_what_already_ran():
    from nucleo.turn.prompt import live_record
    assert "agenda:clear_range" not in "\n".join(live_record.done_ops_lines())
    done_ops.note("agenda", "clear_range", {"from": "2026-09-17", "to": "2026-09-17"},
                  n=11, destructive=True)
    assert "agenda:clear_range" in "\n".join(live_record.done_ops_lines())


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
