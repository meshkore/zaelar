"""nucleo/errands/ — an errand with a THIRD PARTY that outlives the turn (V2-683).

The operator's errand: «contacta con Iván Musikin y mantén una conversación con él para organizar una
reunión esta tarde… y cuando él conteste, ahora o dentro de diez horas, sigue esa conversación». Four
kinds of «ongoing» already existed and none of them can hold that:

  · the TURN — seconds.
  · the WORKER SESSION (`nucleo/workers/session.py`) — minutes, in RAM; a restart buries it
    (`rehydrate.py` calls anything older than `STALE_S` archaeology).
  · the CRON (`nucleo/scheduler.py`) — fires a prompt at a time and carries no state of its own.
  · the HARNESS GOAL (`nucleo/harness.py`) — the right shape, capped at five minutes, RAM, and its only
    verifier reads whether a widget is empty.

So this is the missing noun, and it is a RECORD rather than a process: it survives a restart because it is
a row, and it is woken by the world rather than by sitting in memory waiting.

## What it is not

Not a workflow engine. There are no steps here, no branches and no retries — that is the script the
brain-worker doctrine forbids, and it is what makes «reservar una mesa» need a second engine next month.
What this holds is the STATE of an errand; what to say and when to stop is briefed (row 5) and decided by a
model (row 4), inside a mandate the operator granted once.

Not memory either. Nothing here is a fact about the operator: it is process state, the same boundary
`rehydrate.py` draws for its own trail, and it lives in its own table rather than in a pill.

## The two rules that keep it from becoming a nuisance

1. **It is born from HIS OWN ORDER.** An errand comes to exist only from a `send_to` that really went out,
   and `send_to` is only ever called while executing something the operator just asked for. It shipped
   confirm-gated, so his YES to that question WAS the mandate — and on 2026-09-14 he removed the question
   (V2-692): «si yo específicamente digo que se haga una acción y eso requiere mandar un mensaje,
   obviamente ese permiso pasa ya por hecho». The mandate is now the order itself. What did NOT change is
   the bound: an errand answers on the ONE conversation it was born in, and `reply` — answering something
   that arrived on its own — is still gated, because that one is nobody's order.
2. **It closes itself.** His words: «tampoco hay que abrir una tarea y dejarla abierta, porque esa persona
   puede no contestar nunca más». Three exits — the objective verifies, the deadline passes, or he says so
   — and a closed errand releases its conversations, so a message six weeks later about something else
   does not wake something that is over.
"""
from __future__ import annotations

import json
import re
import secrets
import time

from loguru import logger

#: Live states, in the order an errand walks them. `gathering` exists for an errand that is waiting on the
#: OPERATOR (a datum only he can give) rather than on the other party.
LIVE = ("gathering", "contacting", "negotiating", "agreed")
#: Terminal states. `closed` = the objective was met; `abandoned` = nobody answered in time; `blocked` = the
#: other party asked for something only the operator can settle.
DONE = ("closed", "abandoned", "blocked")

#: How long an errand keeps trying after the window the operator named, and the ceiling nothing may pass.
#: Both are DEFAULTS the playbook layer (row 5) overrides; they live here so an errand opened before that
#: layer exists still closes itself.
GRACE_S = 24 * 3600
MAX_S = 7 * 24 * 3600
DEFAULT_WINDOW_S = 4 * 3600

#: «en las próximas cuatro horas» / «within 3 hours». A GRAMMAR, not an intention: a number beside the word
#: for hours or days is the same fact in any sentence that carries it, and it is the operator's own bound.
#: Everything vaguer («esta tarde», «pronto») deliberately falls through to the declared default rather than
#: being guessed at — `scheduler.parse_when` makes the same call for the same reason.
_HOURS_RE = re.compile(r"\b(\d{1,3})\s*(horas?|hours?|h)\b")
_DAYS_RE = re.compile(r"\b(\d{1,2})\s*(d[ií]as?|days?)\b")
_WORD_HOURS = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
               "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_WORD_HOURS_RE = re.compile(r"\b(" + "|".join(_WORD_HOURS) + r")\s*(horas?|hours?)\b")


def _memory():
    """The errands' own facade inside the memory package (`memory/errands_store.py`). Same boundary
    `nucleo/workflows/` keeps — nothing here touches `db`, the schema or the retriever — and it is a
    separate module rather than more of `memory/api.py` because that file is at its size ceiling and the
    ratchet asks for a module instead of a bigger number."""
    from memory import errands_store
    return errands_store


def new_id() -> str:
    """Unpredictable on purpose. `escalate._seq` restarts at 0 in every process, and an id that repeats
    across restarts is how V2-259's errand landed in the previous session's sheet — here it would be how a
    conversation binds to somebody else's errand."""
    return f"e{int(time.time() * 1000) % 10_000_000}-{secrets.token_urlsafe(5)}"


def window_from(text: str, default_s: float = DEFAULT_WINDOW_S) -> float:
    """The bound the operator put on this errand, in seconds, or the declared default."""
    n = (text or "").lower()
    m = _HOURS_RE.search(n) or _WORD_HOURS_RE.search(n)
    if m:
        raw = m.group(1)
        hours = _WORD_HOURS.get(raw, 0) or int(raw or 0)
        if 0 < hours <= 24 * 14:
            return float(hours) * 3600.0
    m = _DAYS_RE.search(n)
    if m and 0 < int(m.group(1)) <= 30:
        return float(int(m.group(1))) * 86400.0
    return float(default_s)


# ── the ledger ──────────────────────────────────────────────────────────────────────────────────────────
def start(objective: str, *, kind: str = "", mandate: dict | None = None, title: str = "",
          window_s: float = 0.0, done_when: dict | None = None, unknowns=None,
          trace: str = "", now: float | None = None) -> dict | None:
    """Open an errand. Returns the row, or None when it must not exist at all.

    The ONE door, and it is self-sufficient: the kind, the closing condition and what still has to be known
    are read from the playbook here rather than by each caller, so an errand opened from anywhere closes
    itself. (Written after a test caught the other shape: only the bus watcher filled `done_when`, and an
    errand opened by any other path could never verify and could only ever end by running out of time.)

    The refusal is not a formality: `escalate_to_slowbrain` puts the SAME check at the one gateway every
    escalation passes (V2-655), so that an errand about modifying the engine never comes to exist — no
    record, no name, no sheet. This is a second gateway to the same kind of work and inherits the rule.
    """
    obj = (objective or "").strip()
    if not obj:
        return None
    try:
        from nucleo import protected_core
        if protected_core.touches_the_engine(obj):
            logger.warning("errands: refused — an errand about the engine itself never comes to exist")
            return None
    except Exception:  # noqa: BLE001 — the guard failing must not open the door it guards
        return None
    now = time.time() if now is None else now
    # The three clocks are the operator's to set (genesis, overridable per install) and fall back to the
    # constants above, so an errand opened before that layer is readable still closes itself.
    grace, ceiling, default_window = GRACE_S, MAX_S, DEFAULT_WINDOW_S
    kind = (kind or "").strip().lower()
    try:
        from .playbooks import done_when as _pb_done, kind_for, needs as _pb_needs, settings
        cfg = settings()
        grace = float(cfg.get("grace_h", GRACE_S / 3600)) * 3600
        ceiling = float(cfg.get("max_days", MAX_S / 86400)) * 86400
        default_window = float(cfg.get("default_window_h", DEFAULT_WINDOW_S / 3600)) * 3600
        if not kind:
            kind = kind_for(obj)
        if done_when is None:
            done_when = _pb_done(kind)
        if unknowns is None:
            unknowns = _pb_needs(kind)
    except Exception:
        pass
    window = float(window_s) if window_s > 0 else window_from(obj, default_window)
    deadline = now + window
    row = {
        "id": new_id(), "kind": kind or "generic", "title": (title or obj)[:120],
        "objective": obj[:300], "mandate": dict(mandate or {}), "state": "contacting",
        "unknowns": list(unknowns or []), "done_when": dict(done_when or {}),
        "last_inbound": "", "wake_count": 0, "trace_id": trace or "",
        "deadline": int(deadline), "expires_at": int(min(deadline + grace, now + ceiling)),
        "created_at": int(now), "updated_at": int(now), "closed_at": 0, "outcome": "",
    }
    _save(row)
    _emit("🎯 encargo abierto", row)
    return row


def _save(row: dict) -> None:
    """Persist an errand AND mirror it onto the operator's task board (V2-728).

    One function rather than five call sites of `errand_put`, for the reason the board needed rebuilding in
    the first place: a rule each writer has to remember is a rule that ends up missing from one of them.
    The mirror is best-effort — a board that failed to update must never lose the errand itself.
    """
    _memory().errand_put(row)
    try:
        from nucleo import tasks as _tasks
        _tasks.errand_mirrored(row)
    except Exception:  # noqa: BLE001
        logger.debug("errands: no pude reflejar el encargo en el tablero de tareas", exc_info=True)


def get(errand_id: str) -> dict | None:
    return _parse(_memory().errand_get(errand_id))


def live(now: float | None = None) -> list[dict]:
    """Every errand still running, expired ones swept first so nobody reads a dead one as open."""
    sweep(now)
    return [_parse(r) for r in _memory().errands_where(LIVE) if r]


def count_open() -> int:
    """One indexed read — it runs on the hot path, from the context pack's `active()`."""
    try:
        return len(_memory().errands_where(LIVE, limit=50))
    except Exception:
        return 0


def bind(platform: str, chat_id, errand_id: str, contact_id: str = "") -> bool:
    """Give a conversation to an errand. False when another errand already holds it: a thread answered by
    two objectives is how the same person gets two different replies to one message."""
    ok = _memory().errand_bind_thread(platform, chat_id, errand_id, contact_id)
    if not ok:
        # A FINISHED incumbent is not an incumbent. Since V2-705 the binding OUTLIVES the close (see
        # `close`), so the row a new errand collides with is routinely one that is already over — and
        # refusing over it would leave the newborn with no conversation at all, which is the V2-692
        # incident with the roles swapped. A LIVE holder still wins here; displacing one is `claim`'s
        # decision, taken out loud, and never a side effect of binding.
        held = last_for_thread(platform, chat_id)
        if held and str(held.get("state") or "") in DONE:
            ok = _memory().errand_rebind_thread(platform, chat_id, errand_id, contact_id)
    if ok:
        logger.info(f"errands: {errand_id} ahora es dueño de {platform}:{chat_id}")
    else:
        logger.warning(f"errands: {platform}:{chat_id} ya pertenece a otro encargo — {errand_id} no lo toma")
    return ok


def claim(platform: str, chat_id, errand_id: str, contact_id: str = "") -> bool:
    """Give a conversation to a NEWBORN errand, taking it from whatever still holds it (V2-692).

    `bind()` refuses when another errand owns the thread, and that refusal is right — two objectives
    answering one person is how they get two different replies to one message. What was wrong is what the
    caller did with it: nothing. Measured on the second live run (2026-09-14), and it cost the whole session.
    Yesterday's errand had reached `agreed` and never closed (its verifier could not read the agenda — see
    `widgets/agenda/gcal.commit_meeting`), so at 18:52 it still owned the operator's Telegram thread with a
    deadline sixteen hours past. The errand born from his new order got ZERO conversations: it could never be
    woken, never verified, and its only possible ending was to announce that nobody had answered. Meanwhile
    the answer that DID arrive woke the stale errand, against yesterday's objective. He had to drive every
    step of it by hand.

    So a live incumbent YIELDS to an order the operator gave just now — his newest word about this person is
    the current one — and the hand-over is TOLD rather than done quietly: an errand he believes is in flight
    must never end in silence, which is the same rule `watch._report_expired` already keeps.
    """
    if bind(platform, chat_id, errand_id, contact_id):
        return True
    incumbent = for_thread(platform, chat_id)
    if incumbent and str(incumbent.get("id") or "") != str(errand_id):
        close(incumbent["id"], "closed",
              "lo reemplaza un encargo nuevo del operador sobre la misma conversación")
        _tell(f"[SISTEMA] Has abierto una gestión nueva con la misma persona, así que doy por terminada la "
              f"anterior: «{str(incumbent.get('objective') or '')[:90]}». Díselo al operador en una frase.")
    return bind(platform, chat_id, errand_id, contact_id)


def _tell(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


def last_for_thread(platform: str, chat_id) -> dict | None:
    """The errand this conversation belongs to OR most recently belonged to, whatever its state (V2-705).

    `for_thread` is the WAKE door and hides a finished errand on purpose. This is the CONTINUITY door: it
    answers «has anything been arranged in this conversation?», which is a different question and must not
    be answered by the same lookup — reading a closed errand as the owner is exactly how a message six
    weeks later would wake something that is over."""
    return _parse(_memory().errand_for_thread(platform, chat_id))


def commitment_ahead(row: dict | None, now: float | None = None) -> bool:
    """Does this errand hold a commitment that has not happened yet? The operator's own criterion for how
    long a conversation should remember a gestión (2026-09-15): «mientras el compromiso esté por llegar».

    The commitment is `done_when.at` — the slot the errand RECORDED when it booked, the same key `book`
    uses to find its own row. No commitment means nothing is ahead: an errand that ended without arranging
    anything leaves the conversation the moment it closes."""
    at = str(((row or {}).get("done_when") or {}).get("at") or "").strip()
    if not at:
        return False
    try:
        return time.mktime(time.strptime(at, "%Y-%m-%d %H:%M")) > (time.time() if now is None else now)
    except Exception:  # noqa: BLE001
        return False


def _sweep_bindings(now: float | None = None) -> int:
    """Retire the bindings of finished errands whose commitment has passed. Returns how many were retired.

    This is the other half of «the binding outlives the close»: without it, every conversation would carry
    a dead gestión for ever and `bind` would be displacing ghosts. A LIVE errand is never touched here —
    only `close` ends one."""
    n = 0
    for row in (_memory().errands_where(DONE) or []):
        parsed = _parse(row) or {}
        if commitment_ahead(parsed, now):
            continue
        eid = str(parsed.get("id") or row.get("id") or "")
        if eid and _memory().errand_threads(eid):
            _memory().errand_unbind(eid)
            n += 1
    return n


def for_thread(platform: str, chat_id) -> dict | None:
    """The errand a conversation belongs to, or None. Runs per inbound message, so it is ONE indexed read."""
    row = _parse(_memory().errand_for_thread(platform, chat_id))
    if row and row.get("state") in DONE:
        return None                      # a finished errand owns nothing, whatever the binding says
    return row


def threads(errand_id: str) -> list[dict]:
    return _memory().errand_threads(errand_id)


def update(errand_id: str, **fields) -> dict | None:
    """Move an errand forward. Only the fields named travel; the rest of the row is untouched."""
    row = _memory().errand_get(errand_id)
    if not row:
        return None
    row = _parse(row)
    for k, v in fields.items():
        if k in ("state", "title", "objective", "kind", "last_inbound", "wake_count", "unknowns",
                 "done_when", "mandate", "deadline", "expires_at", "outcome"):
            row[k] = v
    _save(row)
    return row


def note_wake(errand_id: str, last_inbound: str = "") -> dict | None:
    """Record that this errand was woken, BEFORE anything is sent: an idempotency mark written afterwards is
    one a crash in between turns into a message delivered twice."""
    row = get(errand_id)
    if not row:
        return None
    row["wake_count"] = int(row.get("wake_count") or 0) + 1
    if last_inbound:
        row["last_inbound"] = str(last_inbound)
    _save(row)
    return row


def close(errand_id: str, outcome: str = "closed", why: str = "", now: float | None = None) -> dict | None:
    """End an errand. Its conversations stop WAKING it and keep REMEMBERING it (V2-705).

    ⚠️ This used to delete the binding, so that «a message six weeks later, about something else entirely»
    could not wake something that is over. That danger is real and is still closed — by `for_thread`, which
    hides a finished errand from the wake path, not by throwing the link away. Deleting it threw away the
    FACT as well, and the operator paid for that on 2026-09-15: the meeting with Cryptonite was booked and
    confirmed, the errand closed, and forty seconds later he wrote «Now cancel the meet and appointment»
    from the other side. That message reached a conversation that no longer knew a gestión had ever
    existed, so it woke nothing, connected to nothing, and died in an inbox whose notify policy is `never`.
    In his words: «no es capaz de conectar una tarea con otra».

    So the binding now outlives the close, and `_sweep_bindings` retires it when the COMMITMENT has passed —
    his own criterion over a fixed window: a conversation remembers its gestión for as long as the thing it
    arranged is still ahead, and goes back to being ordinary mail afterwards.
    """
    row = get(errand_id)
    if not row:
        return None
    now = time.time() if now is None else now
    row["state"] = outcome if outcome in DONE else "closed"
    row["closed_at"] = int(now)
    row["outcome"] = (why or "")[:200]
    _save(row)
    # An errand that arranged NOTHING leaves its conversation on the way out, exactly as it always did —
    # there is no commitment for the thread to remember, so keeping the row would only make a ghost that
    # `_sweep_bindings` has to clean up later. The binding is kept ONLY where it means something.
    if not commitment_ahead(row, now):
        _memory().errand_unbind(errand_id)
    _emit("✅ encargo cerrado" if row["state"] == "closed" else "🕰 encargo terminado", row)
    return row


def reopen(errand_id: str, why: str = "", now: float | None = None) -> dict | None:
    """Bring a finished errand back because its conversation moved again (V2-705). None if there is none.

    A gestión is not over while the thing it arranged is still ahead. The operator wrote «Now cancel the
    meet and appointment» forty seconds after his meeting was booked and confirmed, and the errand that
    had just arranged it was closed — so the one thing in the system that knew what «the meeting» meant
    could not hear him. Reopening is what lets the existing wake machinery answer, with the same mandate
    and the same conversation, instead of a new errand starting from nothing.

    It also pushes the clock out: a row brought back with an expiry in the past is swept on the next beat,
    which would look exactly like being ignored again.
    """
    row = get(errand_id)
    if not row or str(row.get("state") or "") not in DONE:
        return row
    now = time.time() if now is None else now
    out = update(errand_id, state="negotiating", outcome=(why or "reabierto: la conversación sigue")[:200],
                 deadline=int(max(int(row.get("deadline") or 0), now + DEFAULT_WINDOW_S)),
                 expires_at=int(max(int(row.get("expires_at") or 0), now + 24 * 3600)))
    if out is not None:
        try:
            _save({**out, "closed_at": None})
        except Exception:  # noqa: BLE001
            pass
        logger.info(f"errands: {errand_id} REABIERTO — su conversación sigue viva y la cita no ha pasado")
        _emit("↩️ encargo reabierto", out)
    return out


def expiry_why(row: dict) -> str:
    """WHY this errand ran out, in the operator's terms — and it is not one sentence, it is three.

    ⚠️ It used to be «nadie contestó dentro del plazo», for every errand, whatever had happened. The first
    live run reached `agreed` (the other person accepted an hour) and would have expired at 02:25 telling
    him nobody had answered: a plain falsehood about his own gestión, and the expensive direction of it —
    it would have made him believe a deal that WAS closed never happened. The expiry announcement exists
    precisely against believing something false about a gestión in flight (`watch._report_expired`), so
    the one thing it may not do is invent the ending.
    """
    if str(row.get("state") or "") == "agreed":
        return "se acordó con la otra persona y se acabó el plazo sin que quedara confirmado"
    if str(row.get("last_inbound") or ""):
        return "hubo conversación pero no se cerró nada dentro del plazo"
    return "nadie contestó dentro del plazo"


def sweep(now: float | None = None) -> list[dict]:
    """Close what ran out of time. Returns the errands closed by THIS sweep, so the caller can tell him."""
    now = time.time() if now is None else now
    out = []
    for r in _memory().errands_where(LIVE):
        if int(r.get("expires_at") or 0) and now > int(r["expires_at"]):
            parsed = _parse(r) or r
            closed = close(r["id"], "abandoned", expiry_why(parsed), now=now)
            if closed:
                out.append(closed)
    # LAST: a binding kept past its commitment is a ghost, and the errands closed just above are exactly
    # the ones whose conversations must be released now (V2-705).
    try:
        _sweep_bindings(now)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands: barrido de conversaciones: {e!r}")
    return out


# ── what the operator and the brain get to see ──────────────────────────────────────────────────────────
def live_phases(now: float | None = None) -> dict:
    """`{task id → the errand's readable second line}` for the open ones, e.g. «esperando respuesta · quedan 2 h».

    V2-728 — what is left of `board_rows()`. That function SYNTHESISED a whole worker-shaped row per errand so
    the board could show it, which is how the board came to have two row shapes stitched together at the HTTP
    route. The row itself is now mirrored into `tasks` when the errand is written (`_save`), and the only
    thing left that cannot be a stored column is this line: it is derived from a clock, so it is computed
    when read, exactly like a worker's `phase` is.
    """
    now = time.time() if now is None else now
    from nucleo import tasks as _tasks
    out = {}
    for r in live(now):
        left = max(0, int(r.get("deadline") or 0) - int(now))
        out[_tasks.errand_uid(r["id"])] = _phase_line(r, left)
    return out


def _phase_line(row: dict, left_s: int) -> str:
    state = {"gathering": "reuniendo datos", "contacting": "esperando respuesta",
             "negotiating": "acordando", "agreed": "cerrando"}.get(row.get("state") or "", row.get("state") or "")
    if left_s <= 0:
        return f"{state} · fuera de plazo"
    if left_s < 3600:
        return f"{state} · quedan {max(1, left_s // 60)} min"
    return f"{state} · quedan {left_s // 3600} h"


def _parse(row) -> dict | None:
    """A stored row with its JSON columns read back. Never raises: an unreadable column costs a field, and
    the errand still has to be visible and closable."""
    if not row:
        return None
    out = dict(row)
    for k in ("mandate", "done_when", "unknowns"):
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = json.loads(v or ("[]" if k == "unknowns" else "{}"))
            except Exception:
                out[k] = [] if k == "unknowns" else {}
    return out


def _emit(label: str, row: dict) -> None:
    try:
        from voice.observer import emit
        emit("errand", label, text=(row.get("title") or row.get("objective") or "")[:120], role="system",
             extra={"errand": row.get("id"), "kind": row.get("kind"), "state": row.get("state"),
                    **({"trace": row["trace_id"]} if row.get("trace_id") else {})})
    except Exception:
        pass
