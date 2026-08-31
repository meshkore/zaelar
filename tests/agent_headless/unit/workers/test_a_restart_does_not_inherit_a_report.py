"""V2-288 — the worker's private drawer was not private: the first errand after a restart inherited someone else's report.

`workdir.for_task` named the directory ONLY by `task_id`, and `escalate._seq` starts at 0 in every process. Thus
the first errand of every startup is `1` again, lands in the same drawer as the first errand of the previous startup,
and its `informe.json` is still there — `_TTL_S` deliberately keeps it for 48 hours so it can be audited.

Measured in the 2026-08-24 11:11 run, `search-buy-guitar__es`, with the bus events in front: the worker
planned «3 steps: deliver guitar report in the results sheet · verify objective criteria · closeout»
and delivered SIX guitars with real Wallapop URLs **27 seconds after starting, with zero navigations, zero
extractions, and zero searches**. They came from `zaelar-workers/1/informe.json`, written at 03:02 by another run.
And it told the operator «I entered Wallapop and reviewed 14 listings», which is the report's own narrative.

What makes it serious is not that it is a lie, but that it is TRUE from another day: real prices, links that open. An
invented result fails at the first check; this one does not.

It is the same class of issue as the results sheet (V2-259 addendum) and is closed the same way: compose with
`boot_id()`, which also ROLLS on a reset (V2-287) — that way «we start from scratch» truly gets a fresh drawer. Resuming
INSIDE a process is untouched: same stamp, same ID, same drawer.
"""
import json
import os

import pytest

from nucleo import runtime_ids
from nucleo.workers import workdir


@pytest.fixture(autouse=True)
def _own_root(tmp_path, monkeypatch):
    """ISOLATED drawer — this test writes dummy reports and cannot touch the operator's real ones, which are
    the first evidence examined when a delivery goes wrong."""
    monkeypatch.setattr(workdir, "_ROOT", str(tmp_path / "workers"))
    yield


def _restart():
    """What a new process does: the errand counter starts over. `reset_seq` is the SAME gateway used by
    `nucleo/reset.py::reset_all()` (the operator's ⏻) and the one that rolls the stamp since V2-287."""
    runtime_ids.reset_seq("escalate")


def test_the_first_errand_after_a_restart_gets_an_empty_drawer():
    """THE MEASURED CASE: yesterday's errand `1` left its report; today's errand `1` must not be able to see it."""
    ayer = workdir.for_task("1")
    with open(os.path.join(ayer, "informe.json"), "w", encoding="utf-8") as f:
        json.dump({"items": [{"title": "Yamaha F370BL Negra", "price": "100 €"}]}, f)

    _restart()
    hoy = workdir.for_task("1")

    assert hoy != ayer, "el mismo id de encargo devolvió el mismo cajón tras reiniciar"
    assert not os.listdir(hoy), f"el cajón nuevo trae basura de antes: {os.listdir(hoy)}"


def test_the_old_report_is_not_deleted_either():
    """It is not deleted: the report IS the evidence of what a worker actually delivered, and it is the first thing
    examined when a delivery goes wrong. The fix is that it is not INHERITED, not that it disappears (`_reap` limits it
    by AGE, which is a separate decision and remains in effect)."""
    ayer = workdir.for_task("7")
    open(os.path.join(ayer, "informe.json"), "w", encoding="utf-8").write("{}")
    _restart()
    workdir.for_task("7")
    assert os.path.exists(os.path.join(ayer, "informe.json"))


def test_resuming_inside_one_process_lands_back_in_its_own_drawer():
    """The converse case, without which «do not inherit» could be satisfied with an `mkdtemp` that breaks V2-049
    continuity: a relieved or resumed worker must be able to find what it wrote again."""
    a = workdir.for_task("3")
    open(os.path.join(a, "parcial.json"), "w", encoding="utf-8").write("{}")
    b = workdir.for_task("3")
    assert a == b
    assert os.path.exists(os.path.join(b, "parcial.json"))


def test_two_errands_of_one_run_never_share_a_drawer():
    """What the module already promised and continues to fulfill: two live errands at once do not share `informe.json`."""
    assert workdir.for_task("1") != workdir.for_task("2")


def test_the_stamp_is_the_one_the_engine_uses():
    """Composed with the ENGINE's stamp, not a local one. A local stamp would look identical in this test and would not
    roll on a reset, which is precisely half of what makes ⏻ get a fresh drawer."""
    assert runtime_ids.boot_id() in os.path.basename(workdir.for_task("9"))
