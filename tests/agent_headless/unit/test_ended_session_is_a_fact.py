"""A worker SESSION that ends is also a fact (V2-198).

V2-150 fixed this for BROWSER tasks: “a task that ENDS disappeared from the state, so there was no
fact saying that it had ended, much less that it had ended empty… the only thing that could contradict it
had been removed from in front of it.”

The same gap existed one level above, and **it is worse**: a browser task exists only with `kind=web`,
whereas EVERY escalation opens a worker session. Cases resolved by SEARCH
(`cheapest-monitor`) or by MEMORY (`remember-and-remind-deadline`) have no browser task at all,
so the V2-150 fix was never applied to them — and they are exactly the ones the harness has been measuring
as “the user waiting without feedback” and “infinite wait.”

There were also FOUR filters writing `("queued", "running")` by hand, which is the same way V2-197
fixed the browser registry: two lists that have to be kept synchronized are two lists that will not be.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nucleo import dispatch

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()


def _live_session(status: str = "running", goal: str = "Buscar un monitor"):
    r = dispatch.SessionRecord(task_id="w1", goal=goal, kind="generic")
    r.status = status
    dispatch._SESSIONS["w1"] = r
    return r


def _session(status: str, *, ok: bool = True, summary: str = "", goal: str = "Buscar un monitor") -> None:
    """A session that ENDED, through the SAME path as production.

    V2-199 — the first version of this helper put the record in `_SESSIONS` and left it there. It passed, and did not
    test anything: `_run_session` **removes the record in its `finally`**, so in a real dispatch there was nothing
    left to read and `recently_ended_sessions()` returned zero. A real escalation discovered it, not the
    suite. It now calls the same `_remember_ended()` that `finally` calls, and a test requires that this
    location keep calling it."""
    r = _live_session(status, goal)
    r.ok, r.result_summary = ok, summary
    dispatch._remember_ended(r)
    dispatch._SESSIONS.pop("w1", None)          # as `_run_session` does


def _state() -> str:
    from nucleo.flash import prompt as _p
    return _p.live_state()


def test_a_finished_session_does_not_vanish():
    _session("done", summary="3 monitores encontrados")
    assert dispatch.pending_summaries() == []            # it is no longer live…
    assert [r["id"] for r in dispatch.recently_ended_sessions()] == ["w1"]   # …but it IS an ending
    state = _state()
    assert "TAREAS DE FONDO — YA ACABADAS" in state
    assert "3 monitores encontrados" in state            # and with what it brought, which is what the operator wants


@pytest.mark.parametrize("status,ok,marca", [("done", True, "TERMINÓ"),
                                             ("cancelled", True, "se PARÓ (cancelada)"),
                                             ("error", False, "FALLÓ")])
def test_and_each_ending_sounds_like_what_it_was(status, ok, marca):
    """An ending that sounds the same as a different one is useless: “it ended” invites asking for the result, “it stopped” to
    ask whether to resume it, and “it failed” to try something else."""
    _session(status, ok=ok)
    assert marca in _state()


def test_but_a_LIVE_session_is_not_announced_as_ended():
    """The sensitivity check: without this, “say how it ended” and “always say that it ended” behave the same."""
    _live_session("running")
    state = _state()
    assert "YA ACABADAS" not in state
    assert "TAREAS DE FONDO EN CURSO" in state


def test_and_an_old_ending_is_not_this_conversation():
    import time as _t

    _session("done")
    dispatch._ENDED_SESSIONS["w1"]["at"] = _t.time() - (dispatch.JUST_ENDED_S + 60)
    assert dispatch.recently_ended_sessions() == []


def test_the_REAL_path_records_the_ending_before_dropping_the_record():
    """The missing test, and the only one that would have caught the bug: `_run_session` THROWS the record away in its
    `finally`, so reading `_SESSIONS` for endings never finds anything. A real escalation discovered it;
    this fixes it without having to run one."""
    import inspect

    src = inspect.getsource(dispatch._run_session)
    # The LAST pop is the one in `finally`, through which every session that reaches execution exits. The other two are
    # the confirm gate —which has its own state line (V2-126/V2-190), and announcing it as “ENDED” as well
    # would count it twice and incorrectly— and queued cancellation, which does remember.
    i = src.rindex("_SESSIONS.pop(key, None)")
    antes = src[:i]
    # It matches the CALL, not its exact form: V2-222 added `resuming=` and this assert required
    # `_remember_ended(rec)` literally, so it failed because of a new signature even though behavior did not change. What it
    # protects is that the ending is recorded BEFORE the pop; the arguments are the caller's concern.
    assert "_remember_ended(rec" in antes, (
        "`_run_session` tira el registro sin recordar cómo acabó: `recently_ended_sessions()` no verá nada y "
        "el turno volverá a quedarse con su memoria de haber arrancado la tarea.")


def test_and_the_snapshot_does_not_hold_the_worker_handles():
    """A lightweight dict is stored, not the `SessionRecord`: that object carries the worker handles, and keeping it
    alive for five minutes beyond the ending would keep them alive too."""
    _session("done", summary="algo")
    row = dispatch._ENDED_SESSIONS["w1"]
    assert isinstance(row, dict)
    # `sheet` joined in V2-566: the box the errand delivered into, so a follow-up can inherit it — a string,
    # never a handle.
    assert set(row) == {"id", "goal", "status", "ok", "summary", "at", "told", "sheet"}


# ── the enumeration, only once (same lesson as V2-197) ────────────────────────────────────────────────────
_SET = re.compile(r"\.status\s*=\s*[\"']([a-z_]+)[\"']")


def test_the_two_sets_do_not_overlap():
    assert not (dispatch.LIVE_SESSION_STATES & dispatch.ENDED_SESSION_STATES)


def test_every_session_status_the_code_writes_is_classified():
    found: set[str] = set()
    for d in ("nucleo", "server", "voice"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                found |= set(_SET.findall(py.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    known = dispatch.LIVE_SESSION_STATES | dispatch.ENDED_SESSION_STATES
    # `.status = "x"` is a broad pattern: only those declared by SessionRecord itself are required.
    declared = {"queued", "running", "done", "error", "cancelled", "relevada"}
    unclassified = sorted((found & declared) - known)
    assert not unclassified, (
        f"unclassified SESSION states: {unclassified}. A session in that state does not appear in the "
        "live state —neither live nor ended— and the turn is left with its memory of having started it.")


def test_and_nobody_enumerates_them_by_hand_anymore():
    """Four filters each wrote `("queued", "running")` independently. This is exactly how `cancelled` was
    left out of the browser registry (V2-196)."""
    src = (ROOT / "nucleo" / "dispatch.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    code = code.replace('LIVE_SESSION_STATES = frozenset({"queued", "running"})', "")
    assert '"queued", "running"' not in code
