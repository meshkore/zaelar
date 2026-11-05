"""nucleo/circuit/ — what «done» means for a request, owned in one place (V2-776 L3, refactor2710-02).

  · `verdict.py` — the one vocabulary a request ends in; `spec.py` — its end state (inline actions and errands);
  · `verify.py` — the readers of the product's truth; `harness.py` — the card-content goals a reply claims;
  · `ledger.py` — the durable task rows; `deliverable.py` — an errand opens only its deliverable;
  · here — the pulse and a worker's ending: re-verify every open spec, JUDGE an ending (never the worker's word),
    relaunch within the operator's bound (genesis `circuit.retries`), and say the VERDICT.

`None` (unreadable) is never failure and never opens a retry: the cure for unreadable is a readable widget, not a
guess. An ending that cannot be read is `unverifiable`, and the mouth says it as such.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from loguru import logger

from nucleo.circuit import breadth as _breadth
from nucleo.circuit import verdict as _verdict

_GENESIS = Path(__file__).resolve().parents[1] / "genesis.json"
RETRIES_DEFAULT = 2                 # «hemos probado dos o tres veces, no somos capaces» — the operator, 2026-09-29
CHECK_EVERY_S = 5.0                 # an open spec is read at most this often by the pulse
INLINE_GRACE_S = 20.0               # an inline action's end state is owed within this; past it, unmet is the verdict


# ── the bound is the operator's ────────────────────────────────────────────────────────────────────────────

def settings() -> dict:
    """`circuit` of genesis, with the per-install override (`<workspace>/config/circuit.json`) on top —
    the same two layers `style`, `consent` and `errands` use."""
    out: dict = {}
    try:
        out.update((json.loads(_GENESIS.read_text(encoding="utf-8")) or {}).get("circuit") or {})
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import workspace as _ws
        p = _ws.root() / "config" / "circuit.json"
        if p.exists():
            got = json.loads(p.read_text(encoding="utf-8")) or {}
            out.update({k: v for k, v in got.items() if not str(k).startswith("_")})
    except Exception:  # noqa: BLE001
        pass
    return {k: v for k, v in out.items() if not str(k).startswith("_")}


def retries() -> int:
    try:
        return max(0, int(settings().get("retries", RETRIES_DEFAULT)))
    except Exception:  # noqa: BLE001
        return RETRIES_DEFAULT


# ── the pulse ──────────────────────────────────────────────────────────────────────────────────────────────

def tick(now: float | None = None) -> list[dict]:
    """Re-verify the open specs; a met one closes with its event. Returns what closed now. No voice: an inline
    action's refusal is said by the turn's own mouth (`turn/reply.of_op`), and a worker's ending speaks through
    `close`."""
    from nucleo.circuit import spec as _spec
    from widgets import effects as _fx
    now = time.time() if now is None else now
    closed: list[dict] = []
    for e in _spec.open_specs(now):
        if e.get("source") == "shown":
            continue                  # the harness's own goals (V2-776 M4): verified and expired by `harness.sweep`
        if now - float(e.get("checked_at") or 0) < CHECK_EVERY_S:
            continue
        e["checked_at"] = now
        try:
            out = _spec.attest(e, now=now)
            if out is True:
                closed.append(e)
                settle(e, verdict="met", now=now)
                if not e.get("task_id") and _fx.leaves(str(e.get("widget") or ""), str(e.get("action") or "")):
                    _say_now(e, "", fact=SENT, verdict="met")   # a worker's errand speaks through its own `close`   # V2-850: the mouth said «started»; the echo is «sent»
            elif out is False and not e.get("task_id") and now - float(e.get("born") or now) >= INLINE_GRACE_S:
                if _fx.leaves(str(e.get("widget") or ""), str(e.get("action") or "")):
                    _settle_unconfirmed_send(e, now)
                else:
                    _settle_unmet_inline(e, now)
                closed.append(e)
        except Exception as ex:  # noqa: BLE001
            logger.debug(f"circuit: attest skipped ({ex})")
    return closed


#: The row states a task ENDS in. `circuit.settle` is their one writer, for every row (V2-851 §3b, node 7.91).
ENDINGS = ("done", "failed", "cancelled")


def settle(entry: dict | None = None, *, row: str = "", verdict: str = "", state: str = "", outcome: str = "",
           now: float | None = None, extra: dict | None = None) -> None:
    """The ONE writer of an ending (`done|failed|cancelled`) for EVERY row — worker, inline, list, mirror — and of a
    spec entry's status. `state` defaults to the verdict's `row_state`; `extra` = more columns of the same write. A
    row that moves into its ending says so ONCE (`task_state`, writer named); a verdict adds its ONE `verdict`
    event. Six functions wrote endings before (V2-851 F0: >1 writer on 9 % of rows); they call this now."""
    v = _verdict.of(verdict) if verdict else None
    state = state or (v.row_state if v is not None and v.ending else "")
    if (verdict and (v is None or not v.ending)) or state not in ENDINGS:
        logger.warning(f"circuit: {verdict or state!r} is not an ending — nothing is settled with it")
        return
    now = time.time() if now is None else now
    try:
        if entry is not None and v is not None:
            entry["status"], entry["met_at"] = v.name, now
            if entry.get("task_id"):
                from nucleo.circuit import spec as _spec
                _spec.persist(entry["task_id"], entry)
        uid = str(row or (entry or {}).get("row") or "")
        if uid:
            _settle_row(uid, state, v, outcome, now, dict(extra or {}))
        elif entry is not None and v is not None:
            _verdict.emit(v, text=outcome, trace=str(entry.get("trace") or ""), source=str(entry.get("source") or ""))
    except Exception as e:  # noqa: BLE001 — a record that could not be written never breaks the turn
        logger.warning(f"circuit: could not settle {verdict or state} — {type(e).__name__}: {e}")


def _settle_row(uid: str, state: str, v, outcome: str, now: float, extra: dict) -> None:
    from nucleo.circuit import ledger as _ledger      # the row ends with the verdict, and a failed one never improves
    _ts = _ledger.store()
    row = _ts.task_get(uid)
    if row is None:
        return                                   # the fence: a row a reset deleted is not one to be closed
    if v is not None and _verdict.keeps(row.get("verdict"), v.name):
        return                                   # a failed op in this request is not undone by a later good one
    said = (outcome or str(row.get("outcome") or ""))[:400]
    moved = str(row.get("state") or "") != state
    _ts.task_patch(uid, state=state, outcome=said, **({"finished_at": int(now)} if moved else {}),
                   **({"verdict": v.name} if v is not None else {}), **extra)
    trace = str(row.get("trace_id") or "")
    if moved:
        _state_event(uid, state, trace)
    if v is not None:
        _verdict.emit(v, text=said, trace=trace, uid=uid, row_kind=str(row.get("kind") or ""))


def _state_event(uid: str, state: str, trace: str) -> None:
    """The ending's own evidence: which row, which state, who wrote it (the battery's C5/C8 read it). Never raises."""
    try:
        from voice import observer
        observer.emit("task_state", f"📌 task {state} (settle)", role="system",
                      extra={"task_id": uid, "state": state, "writer": "settle", **({"trace": trace} if trace else {})})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never decides an ending
        logger.debug(f"circuit: task_state not emitted — {type(e).__name__}: {e}")


#: What he is told when a send's echo lands (V2-850). The turn said «I'll tell you when it's done» — the queue taking it
#: is no receipt (V2-847) — and measured on his engine (2026-11-04) the echo then closed in silence.
SENT = "Ya ha salido: el envío ha quedado confirmado."

#: What he is told when a send's echo never came within the grace (V2-847). Not «unmet»: the connector may still
#: deliver it, and a failure is told by the connector's own failure path the moment it happens.
UNCONFIRMED_SEND = "No me consta que haya salido: no ha llegado la confirmación del envío."


def _settle_unconfirmed_send(e: dict, now: float) -> None:
    """An act that LEAVES whose echo never landed within the grace: `unverifiable`, said ONCE and NOW — the turn may
    already have said «sent», and nobody saw it leave."""
    settle(e, verdict="unverifiable", outcome="sin eco del envío", now=now)
    try:
        from nucleo.circuit import spec as _spec
        _spec._emit("🫥 spec: el envío no ha dado señal tras el plazo — se dice sin confirmar", e)
    except Exception:  # noqa: BLE001
        pass
    if not e.get("reported"):
        _say_now(e, "", fact=UNCONFIRMED_SEND, verdict="unverifiable")


def _say_now(e: dict, missing: str, *, fact: str = "", verdict: str = "unmet") -> bool:
    """V2-776 M3 — an op he ordered ended UNMET. The turn's reply had already streamed when the op landed (the turn
    never waits on a detached op), so whatever it said — «Done.», «There you go.» — he has not been told the truth.
    The repair is a spoken correction as soon as the verdict exists, composed in the agent's language; whether the
    reply «claimed» delivery is not asked, because reading that from its words is a phrase table (`claims_done`
    does not know «Done.») and the operator needs the truth either way. V2-851 F2: said by the out-of-turn mouth, as
    a line of the request's row (`task_id` = the row, once per line). Scheduled on the running loop; False when
    there is none — the row's verdict already holds it."""
    try:
        import asyncio
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    async def _go():
        try:
            from nucleo.pulse import notices
            from nucleo.workers import spoken_delivery as _sd
            goal = str((e.get("turn") or {}).get("text") or e.get("text") or "")
            # Not `missing`: it names fields («youtube.videoId»), and demo pass 71 said «the YouTube video ID is still
            # set the way it was» to the operator. He needs what he asked for and that it did not happen.
            line = await _sd.line(goal, fact or "Lo que pidió no ha quedado hecho: la pantalla no lo muestra.",
                                  ok=verdict == "met", verdict=verdict)
            if line:
                row = str(e.get("row") or "")
                await notices.notify("circuito", line, task_id=row, key="" if row else f"circuit:{e.get('id')}:{verdict}",
                                     kind="info")
        except Exception as ex:  # noqa: BLE001
            logger.debug(f"circuit: spoken correction failed ({ex})")
    loop.create_task(_go())
    return True


def _made_good_later(e: dict) -> bool:
    """A later write of the SAME card action landed after this one was born — the retry that made it good (refactor2710-99:
    «I couldn't set that Wednesday reminder» said after the reminder was set by the next attempt). Said on the timeline."""
    try:
        from nucleo.flash import served_writes
        if not (e.get("widget") and e.get("action")
                and served_writes.landed_since(e["widget"], e["action"], float(e.get("born") or 0))):
            return False
        from nucleo.circuit import spec as _spec
        _spec._emit("↪️ spec: superada por una escritura posterior de la misma acción — no se corrige", e)
        return True
    except Exception as ex:  # noqa: BLE001 — unreadable: the correction is said as before
        logger.debug(f"circuit: made-good check skipped ({ex})")
        return False


def _settle_unmet_inline(e: dict, now: float) -> None:
    """An inline action whose declared end state never came true: the verdict is `unmet`, said ONCE.

    Audit 2026-09-30 (passes 62-69): `tick` closed only met specs, so an unmet one was re-read every 5 s until its
    30-min TTL — 1095 «sin cumplir todavía» events for one `play_result` whose video never changed (pass 69, V2) —
    and nobody retried, asked or spoke. The circuit saw the failure and had no consumer. No automatic retry here:
    an inline op may have side effects, and the model that fired it is the one that can correct it. The next reply
    reads the row's verdict, so it cannot say «done» over it."""
    from nucleo.circuit import verify as _verify
    missing = "; ".join(_verify.missing(e.get("done_when"), now)) or "el objetivo declarado no se cumple"
    settle(e, verdict="unmet", outcome=missing, now=now)
    try:
        from nucleo.circuit import spec as _spec
        _spec._emit("❌ spec: SIN cumplir tras el plazo — se le dice al modelo", e, missing=missing[:300])
    except Exception:  # noqa: BLE001
        pass
    if e.get("reported"):
        return                               # the op was refused and the turn's own mouth said why
    if _made_good_later(e):
        return                               # a later write of the same card action landed: nothing left to correct
    _say_now(e, missing)                     # he ordered it and it did not happen: said NOW, on its row


# ── the ending of a worker ─────────────────────────────────────────────────────────────────────────────────

def _entry_for(rec):
    from nucleo.circuit import spec as _spec
    uid = str(getattr(rec, "uid", "") or "")
    for e in _spec.open_specs():
        if uid and e.get("task_id") == uid:
            return e
    return None


def _emit(rec, verdict: str, *, missing: str = "", tries: int = 0) -> None:
    try:
        from nucleo.circuit import verify as _verify
        from voice.observer import emit
        label = {"met": "✅ circuito: estado final CUMPLIDO y verificado",
                 "started": "🔁 circuito: sin cumplir → relanzada con lo que falta",
                 "unmet": "❌ circuito: sin cumplir y sin más intentos — se dice lo que falta",
                 "unverifiable": "🫥 circuito: no verificable — se entrega como NO comprobado",
                 "undeclared": "🤷 circuito: sin condición declarada — no se afirma nada",
                 "skipped": "⏭ circuito: no se juzga (cancelada o relevada)"}.get(verdict, verdict)
        emit("task", label,
             text=_verify.describe(getattr(rec, "done_when", None)) or str(getattr(rec, "goal", "") or "")[:120],
             extra={"id": getattr(rec, "task_id", ""), "uid": getattr(rec, "uid", ""), "verdict": verdict,
                    "tries": tries, "missing": missing[:300], "cat": "circuit"})
    except Exception:  # noqa: BLE001
        pass


def verdict_of(rec, now: float | None = None) -> tuple[str, str]:
    """(verdict, what is missing) for a record, with NO side effects — what a budget kill or a stuck worker
    asks before it closes, so the operator hears the end state and not only the clock."""
    from nucleo.circuit import verify as _verify
    dw = getattr(rec, "done_when", None) or {}
    if not dw:
        # Demo pass 62, T1: a trip plan's end state is the REPORT — nothing a widget attests — and «unverifiable»
        # made the delivery say «I couldn't verify the prices myself». An errand whose spec could not be written is
        # one whose result is its words: undeclared. «Unverifiable» is a DECLARED clause the product cannot read.
        return "undeclared", ""
    try:
        from nucleo.circuit import spec as _spec
        dw = _spec.bind_sheet(dw, getattr(rec, "sheet", ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        met = _verify.check(dw, now)
    except Exception:  # noqa: BLE001
        met = None
    if met is True:
        from nucleo.circuit import continuation as _cont
        met = None if _cont.met_at_birth(rec) else met     # already true when its commission was born (V2-835)
    if met is True:
        return "met", ""
    if met is None:
        return "unverifiable", ""
    return "unmet", "; ".join(_verify.missing(dw, now)) or "el objetivo declarado no se cumple"


def close(rec, relay_cap: int) -> str:
    """Judge a worker's ending against its spec and act on it. Returns the verdict; mutates `rec` (`ok`,
    `result_summary`, `handoff`, `verdict`). Never raises.

    The shape `workers/goal.py` had, with the bound made explicit and its own: `tries` lives on the spec
    (persisted on the task row), `genesis.circuit.retries` says how many, and a record that already spent its
    retry (`goal_retried`, the legacy flag a relay carries) counts as one try spent."""
    try:
        return _close(rec, relay_cap)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"circuit: could not judge the ending of {getattr(rec, 'task_id', '?')}: {e}")
        return "undeclared"


def _close(rec, relay_cap: int) -> str:
    from nucleo.circuit import spec as _spec
    if getattr(rec, "status", "") == "cancelled" or getattr(rec, "handoff", ""):
        rec.verdict = "skipped"
        return "skipped"
    verdict, missing = verdict_of(rec)
    entry = _entry_for(rec)
    tries = int((entry or {}).get("tries") or 0) + (1 if getattr(rec, "goal_retried", False) else 0)
    # An INFERRED spec is the model's guess at the end state, never the operator's words (demo pass 64: the INIT list
    # was given «contactos.contacts[title~=Richard]»). A guess may say «unverified»; it may never relaunch an errand
    # — a relaunch repeats side effects — nor tell him the errand failed.
    _src_entry = entry or _spec.of_task(str(getattr(rec, "uid", "") or "")) or {}
    if verdict == "unmet" and "inferred" in str(_src_entry.get("source") or ""):
        verdict, missing = "unverifiable", ""
    # V2-840 H2 — the brief's own target is part of the end state: a model judged the shortfall NOT enough.
    gap = _breadth.another_round(rec) if verdict in ("met", "unverifiable", "undeclared") else ""
    if gap and tries < retries() and int(getattr(rec, "relay_gen", 0) or 0) < relay_cap:
        verdict, missing = "unmet", gap
    elif verdict in ("met", "unverifiable", "undeclared"):
        gap = ""
        _breadth.note_delivery(rec)            # a short delivery says why on the sheet — never held back
    if verdict == "unmet":
        budget = retries()
        if tries < budget and int(getattr(rec, "relay_gen", 0) or 0) < relay_cap:
            # ITERATE — carrying WHAT IS MISSING, so the relaunch starts from the gap instead of from zero.
            rec.goal_retried = True
            try:
                from nucleo.acts import errand as _esc
                _esc.escalate_to_slowbrain(
                    f"{rec.goal}\n\n[ARNÉS] Esto quedó SIN cumplir y es lo que hay que terminar: {missing}. "
                    f"Lo demás ya está hecho: no lo repitas.",
                    context={"src": "goal_unmet", "kind": rec.kind, "trace": rec.trace_id,
                             "sheet": str(getattr(rec, "sheet", "") or ""),
                             "surface": str(getattr(rec, "surface", "") or ""),
                             "done_when": dict(rec.done_when), "depth": int(rec.depth or 0),
                             "relay_gen": int(rec.relay_gen or 0) + 1,
                             "task_uid": str(getattr(rec, "uid", "") or ""),
                             **({"resume": {"brief_task": str(getattr(rec, "uid", "") or rec.task_id)}} if gap else {})})
                rec.result_summary = ""            # no delivery: the relay takes it over, without noise
                rec.ok = False
                rec.handoff = f"objetivo sin cumplir → retomada ({missing[:80]})"
                verdict = "started"                # a relaunch is a new start (tries ≥ 1)
                if entry is not None:
                    entry["tries"] = tries + 1
                    _spec.persist(entry["task_id"], entry)
                logger.warning(f"worker[{rec.task_id}]: objetivo SIN cumplir → relanzada ({tries + 1}/{budget}) · {missing}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{rec.task_id}]: no pude relanzar por objetivo: {e}")
                rec.ok = False
                verdict = "unmet"
        else:
            # No budget left: the operator hears the TRUTH — an errand nobody could finish is never delivered
            # as a finished one, and what it DID achieve is not thrown away.
            rec.ok = False
            rec.result_summary = (f"No he podido dejarlo terminado. Queda: {missing}."
                                  + (f" {rec.result_summary.strip()}" if rec.result_summary.strip() else ""))
            verdict = "unmet"                      # no tries left: what was «gave_up» (tries_left = 0)
            # …and ONE question, once (the operator, 2026-09-29: «acabar de definir mejor la request… después de
            # cada iteración»): the relaunch is PARKED on his answer through the confirm-gate's own register, so
            # his «sí» — with whatever he adds — is what launches it, and silence lets it expire.
            if entry is not None:
                entry["tries_left"] = 0
                if bool(settings().get("ask_on_give_up", True)) and not entry.get("asked"):
                    if _park_retry(rec, missing):
                        entry["asked"] = True
                        rec.result_summary += " " + RETRY_QUESTION
    rec.verdict = verdict
    _emit(rec, verdict, missing=missing, tries=tries)
    _v = _verdict.of(verdict)   # EVERY ending closes its entry, or the pulse re-reads it for its TTL (T-19 R6)
    if entry is not None and (verdict == "unmet" or (_v and _v.ending and _verdict.of(entry.get("status")) is _verdict.STARTED)):
        settle(entry, verdict=verdict, outcome=missing)          # the entry, persisted, and its one verdict event
    else:
        _verdict.emit(_verdict.of(verdict) or _verdict.UNDECLARED, text=missing,
                      trace=str(getattr(rec, "trace_id", "") or ""), uid=str(getattr(rec, "uid", "") or ""), tries=tries)
    return verdict


RETRY_QUESTION = "¿Lo intento otra vez, con alguna pista tuya?"


def _park_retry(rec, missing: str) -> bool:
    try:
        from nucleo.dispatch import confirm as _dc
        _dc.remember_offer(
            f"{rec.goal}\n\n[ARNÉS] Esto quedó SIN cumplir y es lo que hay que terminar: {missing}. "
            f"Lo demás ya está hecho: no lo repitas.",
            context={"src": "goal_unmet", "kind": rec.kind, "trace": rec.trace_id,
                     "sheet": str(getattr(rec, "sheet", "") or ""), "surface": str(getattr(rec, "surface", "") or ""),
                     "done_when": dict(rec.done_when), "depth": int(rec.depth or 0),
                     "task_uid": str(getattr(rec, "uid", "") or "")},
            question=f"No he podido dejarlo terminado: queda {missing[:160]}. {RETRY_QUESTION}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"circuit: could not park the retry: {e}")
        return False


def ending_note(rec, now: float | None = None) -> tuple[str, str]:
    """(verdict, missing) for an ending the pulse forces (a budget kill, a stall): what the operator hears
    beside the clock — the END STATE, which is the thing he asked about. No side effects."""
    return verdict_of(rec, now)


# ── the mouth ──────────────────────────────────────────────────────────────────────────────────────────────

def outcome_line(verdict: str, ok: bool) -> str:
    """The outcome sentence the spoken delivery is built on — the verdict's, never the worker's `ok`."""
    v = _verdict.of(verdict)
    if v is not None and v.instruction:
        return v.instruction
    return "It is done." if ok else "It could not be completed."


def voice_rules_line() -> str:
    """The operator's standing rules for how the assistant speaks (scope `voice`), so a delivery composed off
    the turn obeys them like a turn does — `proactive.notify` never read them."""
    try:
        import rules.notes as _rnotes
        rs = _rnotes.for_surface("voice")                        # V2-806: rows of the rules table
        if not rs:
            return ""
        return "The person's standing rules for how you speak, which you obey: " + " · ".join(str(r)[:160] for r in rs[:6])
    except Exception:  # noqa: BLE001
        return ""

# ── an errand opens only its DELIVERABLE on his screen (V2-822; was `deliverable_gate.py`) ──────────────────────
# A worker's `show_widget` was a free door to any card: when the errand's surface names its card (the results sheet
# for a list, the document for a report, the viewer for pictures), a show of any OTHER card is refused, with the way
# through — read it without opening it, deliver into the deliverable. An errand that delivers no card opens nothing;
# one that builds or fills a card of his opens that card. Reading, writing and closing are never refused.

def not_the_deliverable(rec, wid: str) -> str | None:
    """None when an errand may show `wid` (it IS or carries the deliverable), else its deliverable card ("" = none).
    The ONE licence of an errand's show (refactor2710-15): the Request's surface, never the worker's words."""
    from nucleo import surfaces
    surface = str(getattr(rec, "surface", "") or "")
    own = surfaces.deliverable_card(surface)
    wid = str(wid or "").split("::", 1)[0].strip().lower()
    if not wid or wid in _end_state_cards(rec):
        return None
    if surfaces.delivers_no_card(surface):
        return ""
    return None if (not own or wid == own) else own


def errand_of(src: str):
    """The errand a canvas act comes from (`worker:<task>`, or `sheet:<sheet>` its search fills), else None."""
    kind, _, ref = str(src or "").partition(":")
    if not ref:
        return None
    from nucleo.dispatch import registry
    if kind == "worker":
        return registry.get_record(ref)
    if kind == "sheet":
        from nucleo import dispatch as _d
        return next((r for r in _d._SESSIONS.values() if str(getattr(r, "sheet", "") or "") == ref), None)
    return None


def a_step_not_a_show(src: str, wid: str, *, emit=None) -> bool:
    """True when an errand's show is one of its STEPS, not its deliverable: told as a `step`, nothing opens."""
    try:
        rec = errand_of(src)
        if rec is None or (own := not_the_deliverable(rec, wid)) is None:
            return False
        if emit is None:
            from voice.observer import emit
        task = str(getattr(rec, "task_id", "") or "")
        emit("step", "↳ a step of the errand, kept off his screen", role="system",
             extra={"id": wid, "deliverable": own, "task": task, "src": src})
        return True
    except Exception as e:  # noqa: BLE001 — an unreadable errand never hides a card: the show goes on
        __import__("logging").getLogger(__name__).debug("deliverable licence unreadable: %s", e)
        return False


def refused(rec, action: str, payload: dict) -> str:
    """Why this `show_widget` is refused ("" = let it through), said to the worker with the way through."""
    if action != "show_widget" or not isinstance(payload, dict):
        return ""
    wid = str(payload.get("id") or payload.get("widget_id") or "").split("::", 1)[0].strip().lower()
    if (own := not_the_deliverable(rec, wid)) is None:
        return ""
    _refusal_event(rec, wid, own)
    if not own:
        return (f"this errand delivers no card — its result is told (or simply done), so it opens nothing on his "
                f"screen and «{wid}» stays closed. Read it with read_widget (nothing opens) and report your result.")
    return (f"this errand's deliverable is the «{own}» card, and it is the only card the errand opens on his screen — "
            f"«{wid}» stays closed. Read it with read_widget (nothing opens) and deliver your result into «{own}».")


def _end_state_cards(rec) -> set:
    """The cards the errand's own END STATE names (`done_when` clauses): when what he asked for is a state of a card
    (the player playing, a row on his list), that card IS the deliverable even if the result is also told."""
    try:
        from nucleo.circuit import verify
        _mode, clauses = verify._clauses(getattr(rec, "done_when", None) or {})
        return {str(c.get("widget") or "").split("::", 1)[0].strip().lower() for c in clauses if c.get("widget")}
    except Exception:  # noqa: BLE001 — an unreadable end state names no card
        return set()


def _refusal_event(rec, wid: str, own: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 a card that is not the deliverable stays closed", role="system",
             extra={"id": wid, "deliverable": own, "task": str(getattr(rec, "task_id", "") or "")})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the bridge
        __import__("logging").getLogger(__name__).debug("deliverable gate emit failed: %s", e)
