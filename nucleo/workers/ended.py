"""nucleo/workers/ended.py — an ENDING is a FACT: session states and the just-ended snapshot store.

Extracted from `dispatch.py` on 2026-09-03 when paying the architecture ratchet (V2-566 added the sheet to the
snapshot plus the follow-up inheritance and the file exceeded its ceiling: the table calls for extracting a
concern, not increasing the number — same payment as `workers/resume.py`, 2026-08-26). It is a COHESIVE concern:
the two state enums, the `_ENDED_SESSIONS` snapshot store and the four operations on it — remember an ending
(`_remember_ended`), list the recent ones (`recently_ended_sessions`), count the turns that already carried one
forward (`mark_death_reported`) and the live-goal filter that keeps a running errand out of the ended block
(`_live_goals`).

`dispatch.py` retains ALIASES with the historical names (`dispatch._ENDED_SESSIONS` is THE SAME dict): external
readers (`flash/prompt.py`, `flash/task_block.py`, `turn_marks.py`, the tests) keep working unchanged. What does
NOT move here is `pending_summaries()`: it projects LIVE sessions for the prompt, and that belongs to the
dispatcher's registry.
"""
from __future__ import annotations

import time

# V2-198 — the states of a worker SESSION, enumerated ONCE. There were FOUR filters writing
# `("queued", "running")` by hand and none for the other side: a session that finishes, is cancelled or fails
# used to vanish from the registry without leaving ANY fact in the live state. It is the same hole V2-150
# closed for browser tasks and V2-196/197 for their states… one level up, and worse: a browser task only
# exists with `kind=web`, while **every** escalation opens a worker session. Cases resolved by search
# (`cheapest-monitor`) or by memory (`remember-and-remind-deadline`) have no browser task at all, so for them
# the V2-150 fix never applied.
LIVE_SESSION_STATES = frozenset({"queued", "running"})
# V2-238 — «relevada» is an ending of its own: the session is gone, but the ERRAND is not. It used to live as
# `error`, and with that the engine announced to the operator a death that had not happened while the relay
# worked.
ENDED_SESSION_STATES = frozenset({"done", "error", "cancelled", "relevada"})
JUST_ENDED_S = 300.0     # five minutes: how long the conversation lasts in which the operator still asks


_ENDED_SESSIONS: dict[str, dict] = {}


def _live_goals() -> set[str]:
    """Goals of the sessions that are RUNNING right now, normalised for comparison (V2-222)."""
    from nucleo import dispatch as _d   # the live registry stays with the dispatcher
    out = set()
    for r in list(_d._SESSIONS.values()):
        try:
            if str(getattr(r, "status", "") or "") in LIVE_SESSION_STATES:
                g = (getattr(r, "goal", "") or "").strip().lower()
                if g:
                    out.add(g)
        except Exception:  # noqa: BLE001
            continue
    return out


def _remember_ended(rec, resuming: bool = False) -> None:
    """Snapshot of a session that just ENDED, kept for `JUST_ENDED_S`.

    `resuming` means the caller is about to relaunch this very errand (V2-049 auto-resume), so it did NOT end —
    and recording it as ended is what put two contradictory statements about the SAME errand in one prompt. See
    V2-222 and the measurement in `recently_ended_sessions`.

    V2-199 — V2-198 read `_SESSIONS` for the ended ones and **`_run_session` pops the record in its `finally`**,
    so in a real dispatch there was never anything left to find. Its unit tests placed records by hand and
    never popped, which is why they passed while the production path did nothing: **a test that never walks the
    real path proves the code compiles, not that it works.** Caught by running one real escalation end to end —
    the worker answered, the brain-note went out, and `recently_ended_sessions()` returned zero.

    A light dict on purpose, not the record: `SessionRecord` holds the worker handles, and keeping it alive
    five minutes past the end would keep those alive too.
    """
    if resuming:
        return
    try:
        from nucleo import surfaces
        from nucleo.sheets import sheet_of
        _ENDED_SESSIONS[str(rec.task_id)] = {
            "id": str(rec.task_id), "goal": (rec.goal or "").strip(), "status": str(rec.status or "done"),
            "ok": bool(rec.ok), "summary": (rec.result_summary or "").strip(), "at": time.time(),
            # V2-566 — the BOX the errand was delivering into, so a follow-up of this just-ended errand can
            # inherit it instead of opening a second one beside it. Only when the sheet really was its surface:
            # inheriting a box the errand never wrote to would re-open an empty card for no reason.
            "sheet": (sheet_of(rec) if surfaces.opens_sheet(getattr(rec, "surface", "")) else ""),
            # V2-224 — how many turns have already CARRIED this ending forward. See `mark_death_reported`.
            "told": 0}
        for k in [k for k, v in _ENDED_SESSIONS.items()
                  if time.time() - float(v.get("at") or 0) > JUST_ENDED_S]:
            _ENDED_SESSIONS.pop(k, None)
    except Exception:  # noqa: BLE001
        pass
    # V2-222 — and if it truly DIED, it gets PUSHED. Measured by the harness on `hotel-under-15-days` with the
    # counter over both routes: what is pushed as a system note gets said in the next turn 3 out of 3 times
    # (3 s for the worker's question, 7 s for the wall); what is only RENDERED as a prompt state line, 0 out of
    # 13 — and with V2-221's imperative wording in front all thirteen times. The state line stays (it is the
    # context of the next five minutes); the order travels by the route that actually arrives.
    try:
        if (str(rec.status or "") != "cancelled" and not bool(rec.ok)
                and not str(getattr(rec, "handoff", "") or "")):     # V2-238: a relayed errand has not died
            from voice import brain_notes
            _g = (rec.goal or "la tarea de fondo").strip()[:70]
            brain_notes.push(
                f"[SISTEMA] La tarea de fondo «{_g}» ha MUERTO sin resultado y no se va a reintentar sola. El "
                f"operador no lo sabe: está esperando algo que ya no va a llegar. Díselo EN ESTE TURNO con tus "
                f"palabras y ofrécele una salida concreta —reintentarlo, probar otra vía o dejarlo—; no digas "
                f"«sigo con ello» ni «te aviso en cuanto lo tenga».")
    except Exception:  # noqa: BLE001
        pass


def recently_ended_sessions(now: float | None = None, limit: int = 3) -> list[dict]:
    """Worker sessions that ended RECENTLY, and HOW they ended.

    Mirror of `widgets/navegador/tasks.recently_finished()` (V2-150), whose lesson was: an ending is a FACT,
    and a task that vanishes from the state when it finishes leaves the turn with its own memory of having
    started it. Here the whole thing was missing.

    V2-222 — and an errand that is RUNNING is not an errand that ended, whatever the registry says. Measured
    by the harness on `hotel-under-15-days` (sandbox `20260820-194231`), reading the system prompt of all
    eight turns: seven carried the SAME goal string twice, in the same prompt —

        TAREAS DE FONDO EN CURSO (… NO reinicies ni digas que ya está): «Busca hoteles de 4 estrellas…»
            — abriendo una página… [paso 2/5, 40%] (llevas 64s)
        TAREAS DE FONDO — YA ACABADAS: «Busca hoteles de 4 estrellas…» FALLÓ … DÍSELO EN ESTE TURNO

    — because the first attempt failed, `_remember_ended` archived it, and V2-049 relaunched the SAME errand
    under another id. Both blocks told the truth about different sessions; the operator only had ONE errand.
    The turn answered «sigo esperando resultados», which is the TRUE half: it was not disobeying the
    imperative, it was resolving a contradiction, and no wording of either half could fix that.

    `_remember_ended(resuming=True)` closes it at the source. This filter is the belt: auto-resume is not the
    only way two sessions carry one goal (a repeated escalation does it too), and the failure mode is a prompt
    that argues with itself — invisible unless someone reads it whole, as this one was read.
    """
    now = time.time() if now is None else now
    _live = _live_goals()
    rows = [{**v, "ago_s": int(now - float(v.get("at") or now))}
            for v in _ENDED_SESSIONS.values()
            if (now - float(v.get("at") or 0)) <= JUST_ENDED_S
            and (v.get("goal") or "").strip().lower() not in _live]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]


def mark_death_reported(task_ids) -> None:
    """A turn has already carried the ending of these tasks forward (V2-224).

    The harness measured V2-221's anti-repetition clause over two rounds of the SAME commit and it failed in
    both opposite directions: in one it said it in turn 2 and repeated it in 5, 6, 7, 8 and 9 —V2-189's broken
    record—, and in the other it said it in turn 2 and then DENIED it for seven turns («sigo con ello», «dame
    un momento»). Same clause, same commit, opposite results: that is not a badly placed threshold, it is that
    «did I already tell them?» was never a FACT the prompt had — it was something the model deduced from the
    window.

    WE do know it: we count the turns that carried it forward. And the lesson the harness left while
    diagnosing it governs the wording of the new face — **silencing the repetition is not silencing the
    state**: the announcement stops, the ban on «sigo con ello» stays.
    """
    for tid in (task_ids or []):
        row = _ENDED_SESSIONS.get(str(tid))
        if row is not None:
            row["told"] = int(row.get("told") or 0) + 1
