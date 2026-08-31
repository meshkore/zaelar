"""After a reset, the process HISTORY stays blank — even against the tombstone race.

Seen live by the operator (2026-08-31): he pressed Reset, and «Histórico» showed exactly one entry — the very
search his reset had cancelled, «⊘ … generic · ahora». The design was already right (V2-084: `reset_all` calls
`ledger.clear()`, processes start blank), and the wipe DID run. What survived it was the race: `reset_all` kills
the live workers FIRST and clears after, but a kill is a signal — the dying worker's finish path runs
asynchronously and, milliseconds after the wipe, `record_finish(status="cancelled")` wrote the killed task's own
tombstone into the fresh slate.

Reordering reset_all cannot fix that: the worker's death is not ours to sequence, and any window reopens it. The
fix is a FENCE — `clear()` stamps when the wipe happened, and a record BORN before that instant belongs to the
era the wipe erased, however late it arrives.
"""
import time

import pytest

from memory import db as memdb
from nucleo.workers import ledger


@pytest.fixture(autouse=True)
def _own_db(tmp_path, monkeypatch):
    """The ledger lives in sys_kv — the OPERATOR's, unless pointed elsewhere (the 7.28 rule)."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_the_killed_tasks_tombstone_does_not_survive_the_reset():
    """The exact live sequence: task starts → reset kills it and wipes → the tombstone lands AFTER the wipe."""
    t_start = time.time() - 60
    ledger.record_finish(id="w1", kind="web", goal="una tarea vieja cualquiera", status="done",
                         started_at=t_start - 300, finished_at=t_start - 200)
    assert len(ledger.history()) == 1
    ledger.clear()                                    # the reset
    ledger.record_finish(id="w2", kind="generic",     # the dying worker, milliseconds later
                         goal="Busca especialistas en aparato digestivo (digestólogos) en Soria",
                         status="cancelled", started_at=t_start, ok=False)
    assert ledger.history() == [], \
        "the task the reset killed wrote its own tombstone into the fresh slate — «empezamos de cero» must hold " \
        "against the record arriving late, because the worker's death is not ours to sequence"


def test_a_task_born_after_the_reset_is_recorded_normally():
    """The counterweight: the fence erases an ERA, not the future. The next session's history works as always."""
    ledger.clear()
    ledger.record_finish(id="w3", kind="web", goal="la búsqueda nueva de después del reset",
                         status="done", started_at=time.time(), ok=True)
    h = ledger.history()
    assert len(h) == 1 and h[0]["goal"].startswith("la búsqueda nueva")


def test_rehydrates_interrupted_marks_from_before_the_reset_are_dropped_too():
    """`rehydrate` passes `started_at=None` and the OLD snapshot's time as `finished_at`: after a reset those
    tasks belong to the wiped era just the same — a restart must not resurrect them into a blank history."""
    old_snapshot_at = time.time() - 120
    ledger.clear()
    ledger.record_finish(id="w4", kind="web", goal="lo que estaba en vuelo antes del reset",
                         status="interrumpido", started_at=None, finished_at=old_snapshot_at, ok=False)
    assert ledger.history() == []


def test_a_record_with_no_dates_is_judged_by_arrival_and_kept():
    """Fail-safe: a caller that stamps nothing is judged by when it shows up. Dropping it would silently lose
    real finishes forever after the first reset ever."""
    ledger.clear()
    ledger.record_finish(id="w5", kind="generic", goal="sin fechas", status="done")
    assert len(ledger.history()) == 1


def test_a_broken_fence_read_fails_open():
    """sys_kv unreadable → no fence → record kept. Losing history to a storage hiccup is the worse mistake."""
    ledger.clear()
    import nucleo.workers.ledger as L

    real_kv_get = None
    from memory import api as mem
    real_kv_get = mem.kv_get

    def boom(key):
        if key == L._CLEAR_KEY:
            raise RuntimeError("simulado")
        return real_kv_get(key)

    mem.kv_get, orig = boom, mem.kv_get
    try:
        ledger.record_finish(id="w6", kind="web", goal="con la valla rota", status="done",
                             started_at=time.time())
        assert len(ledger.history()) == 1
    finally:
        mem.kv_get = orig
