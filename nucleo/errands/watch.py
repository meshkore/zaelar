"""nucleo/errands/watch.py — the world's three ways of moving an errand (V2-683).

Watched FROM THE BUS, never from inside the messaging widget or a connector: the same choice the susurro
and the action map made, and for the same reason — zero coupling, and one place that sees every platform
at once. It is driven by the orchestrator loop's beat (`nucleo/loop.py`), so there is no second scheduler
and no task of its own to leak.

## Three signals, in the order they happen

  1. `msg.send` carrying an `objective` — the operator confirmed a message that OPENS a gestión. It is
     remembered, not acted on: an errand must not exist for a message that never left.
  2. `connector.msg_out` carrying that `ref` — the message REALLY went out and the connector resolved
     which conversation it created. THAT is when the errand is born and the thread is bound, in one step.
     (`msg.send_failed` drops the pending birth; the connector has already told him.)
  3. `connector.msg` on a bound conversation — somebody answered. The errand wakes.

## The coalesce, and why it is not optional

Inbound messages reach the bus BEFORE the widget's owner has written them into the thread store (it
triages in ~2 s batches), and the dossier is read from that store. Waking immediately would hand the model
a conversation missing the very message that woke it. So a wake waits `COALESCE_S`, which also turns a
burst of five messages into ONE move — which is what a person would do anyway.
"""
from __future__ import annotations

import time

from loguru import logger

#: Long enough for the owner's triage batch to have landed the message in the thread store.
COALESCE_S = 4.0
#: A birth that never got its echo is dropped rather than kept forever.
PENDING_TTL_S = 300.0
#: How often the memory queue is checked against the CONVERSATION, which is the durable truth.
RECONCILE_S = 30.0

_subs: dict = {}
_pending_births: dict[str, dict] = {}     # ref → the order that will become an errand, if it goes out
_pending_wakes: dict[str, dict] = {}      # errand id → {"at", "inbound"}
_last_reconcile = 0.0


def _ingest():
    from connectors.messaging import ingest
    return ingest


def start() -> bool:
    """Subscribe once. Returns False when the bus or the messaging layer is not there (a self-host without
    connectors), and the whole module then does nothing at all."""
    if _subs:
        return True
    try:
        import bus
        ing = _ingest()
        _subs["send"] = bus.subscribe(ing.TOPIC_SEND)
        _subs["failed"] = bus.subscribe(ing.TOPIC_SEND_FAILED)
        _subs["out"] = bus.subscribe(ing.TOPIC_MSG_OUT)
        _subs["msg"] = bus.subscribe(ing.TOPIC_MSG)
        logger.info("errands: escuchando el bus (envíos, ecos y respuestas)")
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands: sin bus de mensajería ({e!r})")
        _subs.clear()
        return False


def stop() -> None:
    for s in list(_subs.values()):
        try:
            s.close()
        except Exception:
            pass
    _subs.clear()


def _drain(name: str) -> list[dict]:
    sub = _subs.get(name)
    q = getattr(sub, "queue", None)
    if q is None:
        return []
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except Exception:
            break
    return out


# ── the three signals ───────────────────────────────────────────────────────────────────────────────────
def _note_births(now: float) -> None:
    for ev in _drain("send"):
        ref = str((ev or {}).get("ref") or "")
        if ref and str(ev.get("objective") or "").strip():
            _pending_births[ref] = {**ev, "_at": now}
    for ev in _drain("failed"):
        ref = str((ev or {}).get("ref") or "")
        if ref and _pending_births.pop(ref, None) is not None:
            logger.info(f"errands: el mensaje no salió — no se abre encargo para {ref}")
    for ref, row in list(_pending_births.items()):
        if now - float(row.get("_at") or now) > PENDING_TTL_S:
            _pending_births.pop(ref, None)


def _born_from_echo(now: float) -> list[dict]:
    """A message really went out: open the errand and give it the conversation the connector just created."""
    from . import bind, start as _start
    born = []
    for ev in _drain("out"):
        ref = str((ev or {}).get("ref") or "")
        order = _pending_births.pop(ref, None) if ref else None
        if not order:
            continue
        objective = str(order.get("objective") or "")
        # The kind, the closing condition and the unknowns are read by `start()` itself — one door, so an
        # errand opened from anywhere else closes itself too.
        row = _start(
            objective, title=objective[:120],
            mandate={"parties": [order.get("contactId") or ""], "channels": [order.get("platform") or ""],
                     "may": ["message", "schedule"]},
            trace=str(order.get("trace") or ""),
        )
        if not row:
            continue
        bind(ev.get("platform") or order.get("platform"), ev.get("chatId"), row["id"],
             str(order.get("contactId") or ""))
        born.append(row)
    return born


def _note_inbound(now: float) -> None:
    from . import for_thread
    for ev in _drain("msg"):
        platform, chat_id = (ev or {}).get("platform"), (ev or {}).get("chatId")
        if not platform or chat_id is None:
            continue
        row = for_thread(platform, chat_id)
        if not row:
            continue
        mid = str(ev.get("messageId") or "")
        if mid and mid == str(row.get("last_inbound") or ""):
            continue                          # already handled: a re-publication is not a second answer
        _pending_wakes[row["id"]] = {"at": now, "inbound": mid}


def _newest_inbound(platform, chat_id, since: float) -> tuple[str, float]:
    """The id and time of the last message the OTHER side wrote in that conversation, ignoring anything
    older than `since` (an errand must never answer a message that predates its own birth)."""
    try:
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import thread as _thread
        db = msgstore.load()
        th = (db.get("threads") or {}).get(_thread.key(platform, chat_id)) or {}
        for m in reversed(list(th.get("msgs") or [])):
            if str(m.get("dir") or "") != "in":
                continue
            ts = float(m.get("ts") or 0.0)
            return ("" if ts < since else str(m.get("id") or ""), ts)
    except Exception:
        pass
    return "", 0.0


def _reconcile(now: float) -> None:
    """The DURABLE half of the wake queue: what the conversation already holds and the errand never answered.

    `_pending_wakes` lives in memory, and the bus is a notification, not a record. The first live run
    (2026-09-13, V2-684) lost a real answer exactly there: three messages arrived at 22:28, the engine was
    restarted at 22:33, and the errand stayed in `contacting` for ever with `last_inbound` empty — nobody
    ever asked the thread store what it was already holding, so the only thing that could have moved it was
    that person happening to write a fourth time. The same hole swallows an answer that lands while the ⏻
    is off for longer than one process, and any bus event dropped anywhere in between.

    So every `RECONCILE_S` this compares each live errand's `last_inbound` against the newest inbound of the
    conversations it owns and owes itself a wake when they disagree. It is a cheap read of a file the widget
    keeps loaded, and it makes the bus an OPTIMISATION — the fast path — instead of the only path.
    """
    global _last_reconcile
    if now - _last_reconcile < RECONCILE_S:
        return
    _last_reconcile = now
    from . import live, threads
    for row in live(now):
        eid = str(row.get("id") or "")
        if not eid or eid in _pending_wakes:
            continue
        seen = str(row.get("last_inbound") or "")
        born = float(row.get("created_at") or 0.0)
        for t in threads(eid):
            mid, _ts = _newest_inbound(t.get("platform"), t.get("chat_id"), born)
            if mid and mid != seen:
                logger.info(f"errands: {eid} tiene una respuesta sin atender en "
                            f"{t.get('platform')} — la recojo de la conversación")
                _pending_wakes[eid] = {"at": now, "inbound": mid}
                break


# ── the beat ────────────────────────────────────────────────────────────────────────────────────────────
async def tick(now: float | None = None) -> None:
    """One pulse, called by the orchestrator loop. Never raises: this must not be able to stop the loop."""
    now = time.time() if now is None else now
    if not start():
        return
    try:
        _note_births(now)
        _born_from_echo(now)
        _note_inbound(now)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: no pude leer el bus ({e!r})")
    try:
        await _fire_wakes(now)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: un despertar falló ({e!r})")
    try:
        _report_expired(now)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands: barrido: {e!r}")
    # LAST, and for the same reason `_report_expired` guards its own order: `live()` sweeps expired errands
    # as a side effect, so reconciling earlier would close the timed-out ones SILENTLY and leave the line
    # above with nothing to announce. A test caught it here too, which is the second time this one bites.
    try:
        _reconcile(now)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands: reconciliación: {e!r}")


async def _fire_wakes(now: float) -> None:
    """One errand at a time, and only once the coalesce window has passed.

    ⚠️ The ⏻ gate is HERE, above the queue, and that is the fix for a defect the first live run found
    (2026-09-13, V2-684): a person answered while the agent was stopped, this loop POPPED the pending wake
    and `wake()` then refused with «parado» — so the answer was not postponed, it was LOST, and the errand
    could only ever move if that person happened to write again. «Postpone, don't lose» is the rule
    (`loop._fire_due` for crons, V2-655 for the interrupted-work trail), and consuming the queue six lines
    before the refusal is exactly how it gets broken. `wake()` keeps its own gate: two of them cost
    nothing, and this one has to survive somebody calling `wake()` from anywhere else.
    """
    from . import get, wake as _wake_mod
    try:
        from nucleo import runstate
        if runstate.blocks_new_work():
            return                            # nothing is consumed: the same wake is due on the next beat
    except Exception:
        return                                # fails CLOSED, like every other reader of this switch
    due = [(eid, row) for eid, row in _pending_wakes.items()
           if now - float(row.get("at") or now) >= COALESCE_S]
    for eid, row in due:
        _pending_wakes.pop(eid, None)
        errand = get(eid)
        if not errand or errand.get("state") in ("closed", "abandoned", "blocked"):
            continue
        await _wake_mod.wake(errand, reason="inbound", inbound_id=str(row.get("inbound") or ""), now=now)


def _report_expired(now: float) -> None:
    """Errands that ENDED on this beat, each told once.

    Two ways to end and they are told differently on purpose: one that was ACHIEVED is announced by the
    thing that checked the product's own truth (`verify.py`), never by the model that hoped so; one that
    ran out of time is announced because closing it in silence would leave him believing a gestión is still
    in flight — the same class of lie as narrating it as done."""
    from . import sweep
    from . import verify as _verify
    # ORDER MATTERS, and a test caught it: `verify.sweep_met` reads `live()`, which sweeps expired errands
    # as a side effect — so running it first CLOSED the timed-out ones silently and left this loop with
    # nothing to announce. The expiry sweep goes first and keeps its own list.
    expired = sweep(now)
    for row in _verify.sweep_met(now):
        try:
            from voice import brain_notes
            brain_notes.push(
                f"[SISTEMA] «{str(row.get('objective') or '')[:90]}» ya está hecho y verificado. "
                f"Cuéntaselo al operador de forma natural, en una frase.")
        except Exception:
            pass
    for row in expired:
        try:
            from voice import brain_notes
            brain_notes.push(
                f"[SISTEMA] Se acabó el plazo de «{str(row.get('objective') or '')[:90]}» y nadie contestó. "
                f"Díselo al operador de forma natural y pregúntale si quiere que insistas.")
        except Exception:
            pass


def wake_now(errand_id: str) -> None:
    """Ask for a wake on the next beat (the operator pushing, a cron firing). Never wakes inline: one
    errand moving at a time is what keeps two answers from crossing in the same conversation."""
    _pending_wakes[str(errand_id)] = {"at": 0.0, "inbound": ""}
