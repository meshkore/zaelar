"""A FINISHED browser task must not still look like it is working (V2-167, second round).

The first V2-167 fix worked on the axis it aimed at: the three browser tasks that used to sit in
`status="working"` forever now reach `status="done"`. But the round measured on 2026-08-19 at 20:44 shows the
state they reach is contradictory, and the contradiction lands exactly where the previous bug did — in what the
FlashBrain reads to describe the task:

    status: "done"   phase: "driving the browser"   phase_active: true   results: null

Which is why the judge, re-reading the same three cases, escalated its wording from "disconnection" to
"hallucinatory continuous-search behavior" and two of the four notes went DOWN (2 → 1). The agent is
still telling the truth about the state it is given; the state just changed which way it lies.

`set_status()` writes `finished` when it moves to a terminal status and leaves `phase`/`phase_active` untouched —
so every terminal path in the module inherits the last phase string the loop happened to set. That is one fix in
one place, not a fix per call site, which is why this is worth a test of its own rather than a note in the
initiative.

The tests below assert the CONTRACT, so they go red until it holds. Marked `xfail` (non-strict) on purpose: the
board's "TODO VERDE" is a signal the operator reads, and a known-open defect should not make it lie either
direction. When the fix lands these XPASS, which is the visible cue to drop the marker.
"""
from __future__ import annotations

import pytest

from widgets.navegador import tasks

_OPEN = "V2-167 sigue abierta: un `status` terminal no limpia la fase"


@pytest.fixture(autouse=True)
def _clean_registry():
    tasks._tasks.clear()
    yield
    tasks._tasks.clear()


def _finished_task(status: str = "done") -> str:
    tid = tasks.create("reservar mesa esta noche", "Mesa · 2 personas")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.set_status(tid, status)
    return tid


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
def test_a_terminal_status_stops_the_phase(status):
    """MEASURED: `status=done` with `phase_active=True` and «driving the browser» still in `phase`.

    Parametrised over the three terminal states because the bug is in `set_status`, not in the happy path: a fix
    that only cleared it for `done` would leave a cancelled or failed task claiming to be driving a browser,
    which is the same lie with a different label.

    CLOSED 2026-08-23 (`set_status` now clears `phase_active` when it enters a terminal state), so the `xfail`
    marker is gone — which is exactly the cue this file's header describes. The measurement that finally forced
    it came from `search-secondhand-monitor__es`: a task read `status="cancelled"` while still carrying
    `phase="paused — resuming management"` and `phase_active=True`, and the round's watchdog fired twice on
    the gap between what the mechanism said and what the state advertised.
    """
    t = tasks.get(_finished_task(status))
    assert t["status"] == status
    assert t["phase_active"] is False, "a finished task cannot still be marked active"


def test_and_what_the_brain_READS_does_not_contradict_itself():
    """The registry is not the surface that matters — `active_progress()` is what reaches the prompt. A finished
    task must not appear there at all. This one ALREADY holds — `active_progress()` filters by status — and the
    test exists so a fix to the contradiction above cannot regress it. Which also narrows where the measured
    failure came from: not from this projection, so the stale phase reaches the turn by another route (the task
    view the card and `recently_finished()` serve), and that is where to look."""
    tid = _finished_task()
    live = [row for row in tasks.active_progress() if row.get("id") == tid]
    assert not live, f"una tarea terminada sigue proyectada como viva: {live}"


@pytest.mark.xfail(reason=_OPEN, strict=False)
def test_a_task_that_ends_with_nothing_says_WHY():
    """The other half of the same round: the tasks now end FAST and EMPTY. Navigation events dropped from 12/4/1
    to 1/1/5 and `results` stayed `null` in all three — so the stall/wall detection fires, the task terminates,
    and the operator gets the same nothing as before, only sooner.

    Ending empty is legitimate (a site blocks, nothing matches). Ending empty with no REASON recorded is not:
    it leaves the turn with nothing to say except that it finished, which is the failure this whole initiative
    is about. `wall` already exists for exactly this and `wall_reason()` already recognises the three measured
    walls — what is missing is that a task cannot reach a terminal state with neither results nor a reason.
    """
    tid = tasks.create("dos entradas para el musical", "Entradas")
    tasks.set_phase(tid, "conduciendo el navegador", True)
    tasks.set_status(tid, "done")
    t = tasks.get(tid)
    assert not t.get("results"), "premisa del test: esta tarea termina sin resultados"
    # NOTE: `t["phase"]` is NOT a reason. The first version of this test accepted «wall OR phase» and PASSED —
    # but it passed because the stale phase («driving the browser») was still there, so it was satisfied by the
    # defect itself. A test that the bug makes green is worse than having no test. The reason must be a declared
    # WALL or a FINAL phase; never an in-flight phase.
    stale = (t.get("phase") or "").lower()
    assert "conduciendo" not in stale, "la fase de vuelo no es una razón: es el bug de arriba"
    assert t.get("wall") or stale, (
        "una tarea que termina sin resultados tiene que dejar dicho POR QUÉ (muro declarado, o una fase final)")


def test_the_wall_vocabulary_still_covers_the_three_measured_pages():
    """Not xfail: this part ALREADY works and the test exists so a fix to the above cannot regress it. The three
    URLs are verbatim from the mechanism reports."""
    assert tasks.wall_reason("https://www.booking.com/index.es.html?aid=304142&chal_t=1787158378677")
    assert tasks.wall_reason("https://www.google.com/sorry/index?continue=https://www.google.com/search")
    assert tasks.wall_reason("chrome-error://chromewebdata/")
    assert not tasks.wall_reason("https://www.thefork.es/restaurant/casa-lucio-madrid/r146247")
