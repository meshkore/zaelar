"""What he asked lately and the days before, and what is pending — read from the record (the circuit's ledger).

Moved from `nucleo/flash/task_block.py` (refactor2710-08b).
"""
from __future__ import annotations

from nucleo.circuit import verdict as _verdict
from nucleo.turn.prompt.live_tasks import _short_note


#: V2-776 M2 — how far back, and how many, requests the prompt carries from the record.
RECENT_WINDOW_S = 6 * 3600.0
RECENT_MAX = 6
RECENT_MAX_CHARS = 700
_STATE_WORD = {"running": "EN MARCHA", "pending": "EN COLA", "waiting": "ESPERA TU RESPUESTA",
               "done": "HECHA", "failed": "FALLÓ", "cancelled": "CANCELADA"}
_VERDICT_WORD = {"met": "comprobado en pantalla", "unverifiable": "sin comprobar", "unmet": "no se cumplió"}


def _ago(secs: float) -> str:
    m = int(max(0, secs) // 60)
    return "ahora" if m < 1 else (f"hace {m} min" if m < 90 else f"hace {m // 60} h")


def recent_lines(now: float | None = None) -> list[str]:
    """V2-776 M2 — what he asked for lately and how each one ended, read from the RECORD (`tasks`), always.

    Replaces `record_lines` (D3), which quoted ONE row and only when both RAM blocks were silent. Manual session
    7850de3f (2026-09-30): the INIT list had finished at 11:19 and an hour later the agent said «it's all still
    running» — the record knew, the conversation did not, and a single fallback line lost to the window. Every
    request that acts is a row now (M1: inline ones included), so the prompt reads the last few rows of the last
    hours, one line each: what it was, its state and the circuit's verdict, when, and what came of it.

    FACTS ONLY. No instruction rides this block, on purpose: the live-task paragraph above is the pattern this
    replaces — a rule stacked per incident. A model that contradicts a correct line here is a bank CASE.

    Not repeated: a worker still running (the live block above says it with its phase), one that ended in the
    last five minutes (the just-ended block says it — with the obligation V2-221/224 attach to a death he does not
    know about yet, which is not a fact and does not belong here), a live third-party errand (the errands pack
    says who, how it is going and the deadline), and a list's own steps (the list is the request).
    """
    import time as _t
    now = float(now if now is not None else _t.time())
    try:
        from nucleo.circuit import ledger as _tasks
        rows = _tasks.recent(since=now - RECENT_WINDOW_S, limit=RECENT_MAX * 4)
    except Exception:  # noqa: BLE001 — a record that cannot be read adds nothing, and never breaks the turn
        return []
    said: set[str] = set()
    live: dict = {}
    try:
        from nucleo import dispatch as _disp
        from nucleo.circuit import ledger as _tasks
        live = {str(x.get("uid") or ""): x for x in _disp.active_sessions() if x.get("uid")}
        said |= {u for u, x in live.items() if str(x.get("status") or "") in ("queued", "running")}
        said |= {_tasks.task_uid(e.get("id")) for e in _disp.recently_ended_sessions(now=now)}
    except Exception:  # noqa: BLE001
        pass
    out: list[str] = []
    used = 0
    for r in rows:
        if r.get("parent_id") or str(r.get("id") or "") in said:
            continue
        if r.get("kind") == "encargo" and r.get("state") in ("pending", "running", "waiting"):
            continue                  # a live errand with a third party: its own block (errands pack) says it whole
        name = _short_note(str(r.get("title") or r.get("goal") or "una petición"), 70)
        st = str(r.get("state") or "")
        bit = f"«{name}» · {_STATE_WORD.get(st, st)}"
        if (v := _VERDICT_WORD.get(getattr(_verdict.of(r.get("verdict")), "name", ""))):   # older rows: «gave_up»
            bit += f" ({v})"
        when = float(r.get("finished_at") or r.get("started_at") or r.get("created_at") or now)
        bit += f" · {_ago(now - when)}"
        det = live.get(str(r.get("id") or "")) or {}
        ask = str(det.get("ask") or (r.get("progress") or {}).get("ask") or "")
        if st == "waiting" and ask:
            bit += f" · te preguntó: «{_short_note(ask, 90)}»"
        elif r.get("outcome"):
            bit += f" · {_short_note(str(r['outcome']), 100)}"
        if used + len(bit) > RECENT_MAX_CHARS and out:
            break
        out.append(bit)
        used += len(bit)
        if len(out) >= RECENT_MAX:
            break
    if not out:
        return []
    return ["LO ÚLTIMO QUE TE HA PEDIDO (registro de peticiones, lo más reciente primero): " + " | ".join(out) + "."]



#: 2026-10-21 — BEFORE the recent window: one line per request of the last days, so «did I give you a list
#: yesterday?» / «what did you do yesterday?» is answered from the record in the turn, not by a worker digging
#: through files for minutes (manual session 374a2ae2: the agent answered «no» to a 26-step list it had finished
#: the day before, then spent four minutes failing to find it). The record knew; the 6 h window did not reach it.
EARLIER_WINDOW_S = 7 * 86400.0
EARLIER_MAX = 5
EARLIER_MAX_CHARS = 420


def _day(ts: float) -> str:
    """A calendar day the way a person names it — weekday AND date («Tuesday 2026-10-20»), so «yesterday» resolves
    to a day and a question about one can be answered for that day, including «nothing that day»."""
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts).strftime("%A %Y-%m-%d")


def _when_label(ts: float, now: float) -> str:
    import datetime as _dt
    return f"{_day(ts)} {_dt.datetime.fromtimestamp(ts).strftime('%H:%M')}"


def earlier_lines(now: float | None = None) -> list[str]:
    """The operator's requests from before `RECENT_WINDOW_S` back to `EARLIER_WINDOW_S`, newest first, one line
    each — what it was, when, how it ended, and for a list how many of its steps were done. FACTS ONLY, like
    `recent_lines`; a list counts once (its steps are its children)."""
    import time as _t
    now = float(now if now is not None else _t.time())
    try:
        from nucleo.circuit import ledger as _tasks
        st = _tasks.store()
        rows = _tasks.recent(since=now - EARLIER_WINDOW_S, limit=EARLIER_MAX * 4, exclude_kinds=("inline",))
    except Exception as e:  # noqa: BLE001 — a record that cannot be read adds nothing, and never breaks the turn
        from loguru import logger
        logger.debug(f"earlier_lines: the request record could not be read: {e}")
        return []
    out: list[str] = []
    used = 0
    for r in rows:
        when = float(r.get("finished_at") or r.get("started_at") or r.get("created_at") or now)
        if r.get("parent_id") or now - when < RECENT_WINDOW_S:
            continue                      # a list's step, or already in the recent block
        name = _short_note(str(r.get("title") or r.get("goal") or "una petición"), 70)
        state = str(r.get("state") or "")
        bit = f"{_when_label(float(r.get('created_at') or when), now)} · «{name}» · {_STATE_WORD.get(state, state)}"
        kids = st.tasks_children(str(r.get("id") or ""))     # a list: its steps are its children
        if kids:
            # What it WAS, in his words: a composed title («26 × Assistant name Johnny») does not answer «the long
            # prompt with several tasks I sent you» — «a list of 26 tasks» that began «DEMO INITIALIZATION» does.
            head = _short_note(" ".join(str(r.get("goal") or "").split()), 60)
            bit += (f" — una lista de {len(kids)} tareas que empezaba «{head}» "
                    f"({sum(1 for k in kids if k.get('state') == 'done')}/{len(kids)} hechas)")
        elif r.get("outcome"):
            bit += f" · {_short_note(str(r['outcome']), 80)}"
        if used + len(bit) > EARLIER_MAX_CHARS and out:
            break
        out.append(bit)
        used += len(bit)
        if len(out) >= EARLIER_MAX:
            break
    # The range is part of the fact (today's date is in the clock line): a day inside it with no line here or in the
    # recent block has nothing on record — the answer to «what did you do yesterday?» when that is the case.
    import datetime as _dt
    since = _dt.datetime.fromtimestamp(now - EARLIER_WINDOW_S).strftime("%Y-%m-%d")
    if not out:
        return [f"Peticiones desde {since}: ninguna."]
    return [f"Peticiones desde {since} (día sin línea = ninguna): " + " | ".join(out) + "."]


def pending_work_lines() -> list[str]:
    """V2-799 — what is pending or stopped, compact (ids + names), ONLY when any row exists; the model resumes from
    it with `resume_task(ids)`. Never breaks a prompt."""
    try:
        from nucleo import pending_work
        return pending_work.prompt_lines()
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"task_block: pending work block skipped ({e})")
        return []
