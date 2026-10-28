"""How many widget data-ops ONE turn runs, and which (V2-391) — one decision shared by both channels.

«ONE per turn» blocked a DUPLICATED `add_meeting` and an ENUMERATION of actions, but two pasted links are two
`add`s (2026-08-27 13:36). So: same widget + same action + different payloads run; an exact duplicate collapses;
another action on the same widget is dropped. Only FAST ops reach here (irreversible ones are CONFIRM).
"""
from __future__ import annotations

import asyncio

import json as _json
import time

from nucleo.flash import op_receipt as _receipt
from nucleo.flash import refusal_line as _rline
from nucleo.turn import verdicts as _verdicts
from nucleo.circuit import compose as _outcome

#: Data-ops per turn. Five pasted links is a request; fifty is a broken model.
MAX_DATA_OPS = 5


def _ident(args: dict) -> tuple[str, str, str]:
    """A data-op's identity: widget + action + payload, comparable."""
    a = args if isinstance(args, dict) else {}
    pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return (str(a.get("widget_id") or "").strip().lower(),
            str(a.get("action") or "").strip(),
            _json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str))


def admite_data_op(args: dict, ya: list[dict], brief=None) -> bool:
    """Does THIS data-op run, given those already run (`ya`)? One decision shared by both channels.
    `brief`: two actions its verdict heard in his sentence are two orders, not a menu (`verdicts.both_heard`)."""
    wid, accion, payload = _ident(args)
    if not wid or not accion:
        return False
    if len(ya) >= MAX_DATA_OPS:
        return False
    for previa in ya:
        p_wid, p_accion, p_payload = _ident(previa)
        if (wid, accion, payload) == (p_wid, p_accion, p_payload):
            return False                      # exact duplicate → the double appointment
        if wid == p_wid and accion != p_accion and not _distinct_targets(args, previa) \
                and not _verdicts.both_heard(brief, wid, accion, p_accion):
            return False                      # another action on the same widget → the enumeration
    return True


def _named(args: dict) -> set[str]:
    """What a data-op names as its object: the non-empty values of its payload, comparable."""
    pl = (args or {}).get("payload") if isinstance((args or {}).get("payload"), dict) else {}
    return {str(v).strip().lower() for v in pl.values() if str(v if v is not None else "").strip()}


def _distinct_targets(a: dict, b: dict) -> bool:
    """Two different actions on one card are two ORDERS when each names its object and they share none (V2-781:
    «play the first one, queue the rest» lost the queue). The enumeration — same row, or none — stays out."""
    na, nb = _named(a), _named(b)
    return bool(na) and bool(nb) and not (na & nb)


# V2-603 — a FAILED data-op must correct the claim already spoken. Ops are fire-and-forget, so the turn speaks
# first (2026-09-06, session e1acdcca: `connect_account` failed with the exact reason; he was told «Hecho.»).
# Same rails as a finished worker (`escalate.py`): voice/proactive + a `[SISTEMA]` note; the widget's own words.

#: Failures already announced (wid:action:error → ts): a card retrying on a timer is not a monologue.
_RECENT_FAILURES: dict[str, float] = {}
_FAILURE_COOLDOWN_S = 90.0


def _dedup(key: str, now: float) -> bool:
    """True if this exact failure was announced within the cooldown. Prunes as it goes."""
    for k, ts in list(_RECENT_FAILURES.items()):
        if now - ts > _FAILURE_COOLDOWN_S:
            _RECENT_FAILURES.pop(k, None)
    if key in _RECENT_FAILURES:
        return True
    _RECENT_FAILURES[key] = now
    return False


async def report_failure(wid: str, action: str, res: dict) -> bool:
    """Announce a FAST data-op that came back `ok: False`. Returns True if the operator was told.
    Best-effort: runs in the op's detached task, so it never raises."""
    import time as _time

    # V2-743 — `error` counts too (2026-09-21, bcd4aba1: a timeout result had no `ok` and was never told); a POOL
    # TIMEOUT does not — the hook keeps running, so `op_receipt` witnesses it instead.
    if not isinstance(res, dict):
        return False
    if _receipt.is_pool_timeout(res) or not _receipt.failed(res):
        return False
    detail = str(res.get("message") or res.get("error") or "").strip()
    if not detail:
        return False
    # V2-652 — `message` is for the operator, `error` for the MODEL (2026-09-10, 7f77e2cc: a retry instruction was
    # spoken aloud). A bare `error` reaches only the note below.
    speakable = _rline.speakable(wid, res)          # the widget's `say` (bundle) or its cleaned `message`
    wid = (wid or "").strip().lower()
    action = (action or "").strip()
    if _dedup(f"{wid}:{action}:{detail}", _time.time()):
        return False

    # An instruction to correct, in his language, carrying the raw detail so it cannot be softened. V2-707 F0: it
    # also says the CORRECTED call will run, or the anti-drag guard and this note leave no legal move (2026-09-16).
    note = (f"[SISTEMA] La acción «{action}» sobre «{wid}» NO se ejecutó. Motivo exacto: {detail}. "
            f"Dilo con naturalidad en tu PRÓXIMA respuesta, en el idioma del operador, y NO digas que está "
            f"hecho. Si el motivo indica que falta un paso suyo, dile cuál es. Si lo que falta es un dato que "
            f"puedes poner tú (cuál de los items, un campo vacío), vuelve a llamar a «{action}» con ese dato "
            f"relleno: la llamada corregida SÍ se ejecuta, no es una repetición.")
    told = False
    try:
        from voice import brain_notes
        brain_notes.push(note)
        told = True
    except Exception:
        pass
    if speakable:
        try:
            # …in the agent's language: widget copy is whatever language it was written in (demo pass 48, V6).
            from nucleo.workers import spoken_delivery as _sd
            said = await _sd.line(f"{wid}: {action}", speakable, ok=False)
            if not said:
                # Demo pass 69, V2: composer empty → raw Spanish copy only to a Spanish agent; else the note covers it.
                try:
                    from i18n import langs as _lg
                    same = str(_lg.current_code() or "es").lower().startswith("es")
                except Exception:  # noqa: BLE001
                    same = False
                said = speakable if same else ""
            if said:
                from voice import proactive
                await proactive.notify("Conector", said, speak=True, kind="notify")
                told = True
        except Exception:
            pass
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op fallida → corregida en voz" if speakable
             else "🩹 data-op fallida → nota al modelo (motivo interno, no se habla)",
             text=detail[:160], extra={"id": wid, "action": action, "told": told,
                                       "spoken": bool(speakable), "is_error": True})
    except Exception:
        pass
    return told


async def corrected_retry(wid: str, action: str, payload: dict, res, text: str, dispatch,
                          said: str = "") -> tuple[dict, dict] | None:
    """ONE corrected re-call of a refused FAST data-op (bounds: `act_repair.call_for_refusal`), shared by both
    channels. Returns `(payload, result)`, `(payload, result, action)` after a card redirect, or None."""
    if not isinstance(res, dict) or _receipt.is_pool_timeout(res) or not _receipt.failed(res):
        return None
    why = str(res.get("message") or res.get("error") or "").strip()
    if not why or not (text or "").strip():
        return None
    from nucleo.flash import parked_refusal as _parked      # the half he supplies next turn completes THIS call
    _parked.remember(wid, action, payload, res)
    try:
        # A refusal naming its alternatives (`res["redirect"]`) is an action to replace, not a payload to correct.
        from nucleo.flash import refusal_redirect as _redirect
        if (alt := await _redirect.retry(wid, action, payload, res, text, dispatch)):
            return alt[1], alt[2], alt[0]                   # it settles the parked refusal itself
        from nucleo.flash import act_repair as _ar
        fix = await _ar.call_for_refusal(text, wid, action, payload or {}, why, said=said)
        if not fix:
            return None
        res2 = await dispatch(wid, action, fix["payload"])
        res2 = res2 if isinstance(res2, dict) else {}
        _parked.remember(wid, action, fix["payload"], res2)   # corrected and landed → nothing parked
        try:
            from voice.observer import emit
            emit("widget", "🔁 data-op rechazada → corregida en el mismo turno", text=why[:160],
                 extra={"id": wid, "action": action, "refused": payload or {}, "payload": fix["payload"],
                        "ok": not _receipt.failed(res2)})
        except Exception:  # noqa: BLE001
            pass
        return fix["payload"], res2
    except Exception:  # noqa: BLE001
        return None


async def refused_unsaid(tasks, timeout: float = 4.0):
    """`(widget, error)` when EVERY op of this turn was refused with only an internal reason, else None.
    Demo pass 104, C5: `send_to` refused with an `error` and the canned ack said «Done.» 10 ms later."""
    try:
        pend = [t for _w, t in tasks if not t.done()]
        if pend:
            await asyncio.wait(pend, timeout=timeout)
        out = None
        for w, t in tasks:
            if not t.done() or t.cancelled():
                return None
            res = t.result()
            if not (isinstance(res, dict) and _receipt.failed(res)) or _rline.speakable(str(w), res):
                return None
            out = out or (str(w), str(res.get("error") or "").strip())
        return out
    except Exception:  # noqa: BLE001
        return None


async def say_refusal_instead(tasks, data_done: dict, send, speech) -> str:
    """Before the canned success ack: when `refused_unsaid`, the turn is NOT done and the reason is SAID, in the
    agent's language. Returns what was said ("" = today's path)."""
    why = await refused_unsaid(tasks)
    if not why:
        return ""
    data_done["v"] = False
    try:
        from nucleo.workers import spoken_delivery as _sd
        from voice.observer import emit
        said = await _sd.line(why[0], why[1], ok=False) or _failed_line()
        emit("brain", "🚫 «hecho» retirado: todas las ops del turno se rechazaron — se dice el motivo", role="system",
             text=f"{why[0]}: {why[1][:140]}", extra={"cat": "flash", "id": why[0], "is_error": True})
    except Exception:  # noqa: BLE001
        said = _failed_line()
    if not said:
        return ""
    send(speech.sanitize(said, drop_metadata=False))
    return said


async def say_owed_after_ops(tasks, data_done: dict, send, speech, timeout: float = 4.0) -> list[str]:
    """The lines this turn OWES its data-ops (`data_done["owed"]`) are said once the ops ANSWERED, never over a
    refusal nor past `timeout`. Audit V2-783 P0-2 (2026-10-16): «Done.» used to follow a refused op. Never raises."""
    owed = [str(line) for line in (data_done.get("owed") or []) if str(line or "").strip()]
    data_done["owed"] = []
    if not owed or not tasks:
        return []
    try:
        pend = [t for _w, t in tasks if not t.done()]
        if pend:
            await asyncio.wait(pend, timeout=timeout)
        for w, t in tasks:
            if not t.done() or t.cancelled():
                return []
            res = t.result()
            if isinstance(res, dict) and _receipt.failed(res):
                try:
                    from voice.observer import emit
                    emit("brain", "🚫 owed line dropped: the op was refused", role="system",
                         text=f"{w}: {str(res.get('message') or res.get('error') or '')[:120]}",
                         extra={"cat": "flash", "id": str(w), "owed": owed[:3]})
                except Exception:  # noqa: BLE001 — the trace never decides the words
                    pass
                return []
    except Exception:  # noqa: BLE001 — unreadable ops claim nothing
        return []
    for line in owed:
        send(" " + speech.sanitize(line, drop_metadata=False))   # sanitize strips the joining space
    return owed


def _failed_line() -> str:
    try:
        from i18n import langs as _lg
        return str(getattr(_lg.current_language(), "op_failed", "") or "")
    except Exception:  # noqa: BLE001
        return ""


async def _say_it_did_not_run(wid: str, action_name: str, exc: BaseException, *, seal=None, row: str = "") -> dict:
    """The op raised before any widget answered: settle its row, forget it as done, and SAY so (V2-778 F0-4).
    Returns the failed result so a caller waiting on it reads a refusal, never an empty success."""
    res = {"ok": False, "message": _failed_line(), "error": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        from voice.observer import emit
        emit("brain", "❌ data-op no se ejecutó", role="system", text=f"{wid}:{action_name} — {res['error']}",
             extra={"id": wid, "action": action_name, "is_error": True, "cat": "flash"})
    except Exception:  # noqa: BLE001
        pass
    if row:
        try:
            from nucleo import circuit as _circuit
            _circuit.settle(row=row, verdict="unmet", outcome=res["error"])
        except Exception:  # noqa: BLE001
            pass
    if callable(seal):
        try:
            seal(False)
        except Exception:  # noqa: BLE001
            pass
    try:
        await report_failure(wid, action_name, res)
    except Exception:  # noqa: BLE001
        pass
    return res


def one_open_instance(wid: str) -> str:
    """V2-773 — a data-op on a BASE id lands on its one open instance (`results::9194df-1`); several keep today's
    path. One home for both channels (V2-778 F4-33)."""
    try:
        from server.voice_api import open_instances as _open_inst
        from widgets import instances as _inst_dt
        return _inst_dt.data_target(wid, _open_inst()) or wid
    except Exception:  # noqa: BLE001
        return wid


def start_op(wid: str, action_name: str, payload: dict, *, seal, text, said, spawn):
    """Start a fast data-op detached, or SAY that it could not start (V2-778 F0-4). Returns the task, or None
    (= NOT done). Was `except: pass` at the call site, leaving «Done.» standing. `text` may be a callable."""
    try:
        t = text() if callable(text) else text
        return spawn(dispatch_and_report(wid, action_name, payload or {}, seal=seal, text=t, said=said),
                     "widget-data")
    except Exception as e:  # noqa: BLE001
        try:
            spawn(_say_it_did_not_run(wid, action_name, e, seal=seal), "widget-data-failed")
            return None
        except Exception:  # noqa: BLE001 — cannot even schedule the report: the model says it next turn
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] La acción «{action_name}» sobre «{wid}» NO se ejecutó "
                                 f"({type(e).__name__}). Dilo en tu PRÓXIMA respuesta y NO digas que está hecha.")
            except Exception:  # noqa: BLE001
                pass
            return None


async def dispatch_and_report(wid: str, action_name: str, payload: dict, *, seal=None, receipt: bool = False,
                              text: str = "", said=None):
    """Dispatch a widget data-op AND announce it if it failed (V2-603). Never raises. `seal` (V2-707 F0) gets
    whether the op HAPPENED, so a refused mutation is never remembered as executed by the anti-drag guard."""
    import widgets
    from nucleo.flash import outgoing_lang as _olang, worker_note_relay as _relay
    if (_to := _relay.relay(wid, action_name, text)):    # a worker's own note: his words go to it (2026-10-14)
        return {"ok": True, "relayed_to": _to}
    payload = await _olang.in_session_language(wid, action_name, payload or {})   # demo pass 106, E3
    # V2-743 — the witness is read BEFORE the op, and only on the `receipt` (confirmed irreversible) path.
    before = await _receipt.read_signature(wid) if receipt else ""
    # V2-776 L1 — the declared postcondition (`done_when`) is opened BEFORE the op, attested after.
    try:
        from nucleo.circuit import spec as _spec
        _spec_entry = _spec.open_for_action(wid, action_name, payload, text=text)
    except Exception:  # noqa: BLE001
        _spec_entry = None
    # V2-776 M1 — the request is a ROW, opened by its first op (`nucleo/request/model.py`).
    try:
        from nucleo.request import model as _rq
        _row = _rq.opened(wid, action_name, text=text)
    except Exception:  # noqa: BLE001
        _row = ""
    if _spec_entry is not None and _row:
        _spec_entry["row"] = _row
        _spec_entry["turn"] = _rq.current()      # his words, for the correction the circuit may have to say
        # V2-778 F3-26 — persisted so a restart can still judge the row; not as `task_id` (that means a worker owns it).
        _spec.persist(_row, _spec_entry)
    # V2-769 — this create's sentence completes an earlier create's piece: revert that row (`circuit/compose.py`).
    if (_prev := _outcome.superseded(wid, action_name, text)):
        await _revert(wid, _prev)
    async def _run(w, a, p):
        return await widgets.dispatch_tag("widget.data", {"id": w, "data": {"action": a, "payload": p or {}}})
    try:
        res = await _run(wid, action_name, payload)
    except Exception as e:  # noqa: BLE001 — V2-778 F0-4: an op that raised is said, never left behind «Done.»
        return await _say_it_did_not_run(wid, action_name, e, seal=seal, row=_row)
    # `said` is read AFTER the refusal, so the correction follows the reply just spoken (demo pass 2026-09-28, S3).
    _said = ""
    try:
        _said = str(said() if callable(said) else (said or ""))
    except Exception:  # noqa: BLE001
        _said = ""
    if not receipt and (_fixed := await corrected_retry(wid, action_name, payload, res, text, _run, said=_said)):
        payload, res, action_name = (*_fixed, action_name)[:3]     # a redirect names the action that ran
    _outcome.remember(wid, action_name, text, res)
    _refused = bool(_receipt.failed(res)) if isinstance(res, dict) else False
    _attested = None
    if _spec_entry is not None:
        try:
            from nucleo.circuit import spec as _spec
            # Only a SPEAKABLE refusal is told by `report_failure`; an `error`-only one is not (V2-652; pass 72, S3).
            _spec_entry["reported"] = _refused and bool(str((res or {}).get("message") or "").strip())
            _attested = _spec.attest(_spec_entry)
        except Exception:  # noqa: BLE001
            pass
    if _row:
        try:
            from nucleo import circuit as _circuit
            if _refused:
                _circuit.settle(row=_row, verdict="unmet", outcome=str(res.get("message") or res.get("error") or "")[:200])
            elif _spec_entry is None:
                _circuit.settle(row=_row, verdict="undeclared")
            elif _attested is not False:
                _circuit.settle(_spec_entry, row=_row, verdict=_circuit.verdict.from_attest(_attested).name)
            elif _spec_entry is not None and _unchanged(_spec_entry):   # a replay, not a failure: the circuit leaves it
                _circuit.settle(_spec_entry, row=_row, verdict="unverifiable",
                                outcome="sin cambio visible: la tarjeta ya estaba así")
            # False: the widget may still be catching up — the circuit's pulse settles it.
        except Exception:  # noqa: BLE001
            pass
    await _report_ignored(wid, action_name, res)
    if not receipt and isinstance(res, dict) and _receipt.is_pool_timeout(res) and res.get("pending"):
        from nucleo.flash import op_pending as _op_pending        # node 2.917: still running, reported when it ends
        return await _op_pending.still_running(wid, action_name, res, seal=seal, row=_row)
    if callable(seal):
        try:
            seal(not (isinstance(res, dict) and res.get("ok") is False))
        except Exception:
            pass
    if receipt:
        # The receipt OWNS the outcome on this path, so `report_failure` must not also speak.
        try:
            await _receipt.settle(wid, action_name, res, before=before)
        except Exception:
            pass
        return res
    try:
        await report_failure(wid, action_name, res)
    except Exception:
        pass
    return res          # the RESULT, for a turn that owes words and waits on it (`answer_of`)


def _unchanged(e: dict) -> bool:
    try:
        from nucleo.circuit import verify as _verify
        return _verify.only_unchanged(e.get("done_when"))
    except Exception:  # noqa: BLE001
        return False


#: The keys every result carries — an ack, not an answer.
_ACK_KEYS = frozenset({"ok", "queued", "id", "error", "message", "widget", "action", "tab"})   # a face's NAME answers nothing


def answer_of(res) -> dict:
    """What a data-op RETURNED beyond its ack, or {} (demo pass 2026-09-28: the Inworld invoice was found and the
    turn said «let me check»)."""
    if not isinstance(res, dict) or _receipt.failed(res):
        return {}
    # A declared answer lives under `result`; the rest is the card's whole view (demo pass 31, R2).
    if isinstance(res.get("result"), dict) and res["result"]:
        out = {"result": res["result"]}
    else:
        out = {k: v for k, v in res.items() if k not in _ACK_KEYS and v not in (None, "", [], {})}
    return out


def answer_to_speak(answers: list, ops) -> tuple | None:
    """The op answer the reply is composed from: the first whose op DECLARES `effects.OUTPUT_ANSWER`, else the
    last. `answers` = [(widget_id, answer)], `ops` = [(widget_id, action)] (demo pass 62, C2)."""
    pairs, ops = list(answers or []), list(ops or [])
    answers = [(w, a) for w, a in pairs if a]
    if not answers:
        return None
    try:
        from widgets import effects as _fx
        if len(pairs) == len(ops):   # demo pass 105, R3: two ops on ONE card — matched by the action, in order
            hit = next(((w, a) for (w, a), (ow, oa) in zip(pairs, ops) if a and _fx.carries(ow, oa, _fx.OUTPUT_ANSWER)), None)
            if hit:
                return hit
        declares = {str(w).split("::", 1)[0] for w, a in (ops or []) if _fx.carries(w, a, _fx.OUTPUT_ANSWER)}
    except Exception:  # noqa: BLE001
        declares = set()
    return next(((w, a) for w, a in answers if str(w).split("::", 1)[0] in declares), answers[-1])


async def _revert(wid: str, prev: dict) -> None:
    """Take out the row a piece of a sentence wrote. Never raises; says so on the timeline either way."""
    import widgets
    rv = prev.get("revert") or {}
    ok = False
    try:
        r = await widgets.dispatch_tag("widget.data", {"id": wid, "data": {
            "action": str(rv.get("action") or ""), "payload": dict(rv.get("payload") or {})}})
        ok = isinstance(r, dict) and r.get("ok") is not False and not r.get("error")
    except Exception:
        pass
    _outcome.forget(wid)
    try:
        from voice.observer import emit
        emit("widget", "🧩 la frase completa sustituye lo que escribió un trozo de ella",
             text=str(prev.get("text") or "")[:120],
             extra={"id": wid, "action": prev.get("action"), "revert": rv, "ok": ok})
    except Exception:
        pass


async def _report_ignored(wid: str, action: str, res) -> None:
    """A write that landed without part of what it was told is corrected, never left standing (V2-769)."""
    note = _outcome.ignored_note(wid, action, res)
    if not note:
        return
    try:
        from voice import brain_notes
        brain_notes.push(note)
    except Exception:
        pass
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op guardada SIN parte de sus datos → nota al modelo", text=note[:200],
             extra={"id": wid, "action": action, "ignored": list(res.get("ignored") or [])})
    except Exception:
        pass


# ── Is this data-op a DRAG from the previous turn? (V2-038 guard, extracted V2-717) ─────────────────────────

def word_overlap(a: str, b: str) -> int:
    wa = {w for w in (a or "").lower().split() if len(w) > 3}
    wb = {w for w in (b or "").lower().split() if len(w) > 3}
    return len(wa & wb)


def is_view_op(wid: str, action: str) -> bool:
    """A LENS, by the widget's own declaration (`"view": true`, V2-545) — the same predicate the canvas arbiter
    reads. Nothing here infers from the name."""
    if not (wid and action):
        return False
    try:
        from widgets import actions as _wactions, runtime
        spec = ((runtime.get(wid.split("::", 1)[0]) or {}).get("actions") or {}).get(action)
        return _wactions.is_view(spec, action)
    except Exception:  # noqa: BLE001
        return False


def is_step_op(wid: str, action: str) -> bool:
    """A STEP, by declaration (`"repeatable": true`, V2-795): the same call again is a new order, never a drag
    («pon la siguiente» twice in 15 s — the second was eaten as context-bleed)."""
    if not (wid and action):
        return False
    try:
        from widgets import runtime
        spec = ((runtime.get(wid.split("::", 1)[0]) or {}).get("actions") or {}).get(action)
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"is_step_op: manifest of {wid!r} unreadable: {e!r}")
        spec = None
    return isinstance(spec, dict) and spec.get("repeatable") is True


#: The last op a widget REFUSED (V2-773: an identical empty `select` refused twice more). Not remembered as
#: DONE (V2-707), so the anti-drag guard cannot see it.
_REFUSED: dict = {"v": None}
_REFUSED_S = 180.0


def repeats_last_view(last, wid: str, action: str, payload: dict | None, *, now: float | None = None,
                      window_s: float = 180.0) -> bool:
    """The SAME lens the card already applied — it yields to the verdict despite V2-754 (demo pass 2026-09-28,
    E2: a repeated `show_view {platform: email}` over a sure `mensajeria:open`)."""
    import time as _t
    try:
        if not last or not is_view_op(wid, action):
            return False
        lw, la, lp, lts = last
        if str(lw).split("::")[0] != str(wid).split("::")[0] or la != action:
            return False
        if ((now if now is not None else _t.time()) - float(lts)) > window_s:
            return False
        mine = {k: v for k, v in (payload or {}).items() if v not in (None, "", [])}
        return all(lp.get(k) == v for k, v in mine.items())
    except Exception:  # noqa: BLE001
        return False


def a_view_where_the_verdict_acts(wid: str, model_action: str, verdict_action: str, words: str) -> bool:
    """The model only LOOKED where the turn asks to DO something else on the same card.
    Demo pass 2026-09-28 (full15 E4): verdict `mensajeria:unread` at 1.00, model `peek`. A lens changes nothing,
    so yielding it under V2-754 costs nothing when the turn wants an act and the verdict names a non-lens."""
    if not (verdict_action and is_view_op(wid, model_action)):
        return False
    if str(words or "") == "tell":
        # …mirror (pass 119, C2: `show_day` under a verdict `find_free`): asked for WORDS, the answering lens wins.
        try:
            from widgets import effects as _fx
            return (_fx.carries(wid, verdict_action, _fx.OUTPUT_ANSWER)
                    and not _fx.carries(wid, model_action, _fx.OUTPUT_ANSWER))
        except Exception:  # noqa: BLE001
            return False
    if str(words or "") != "act":
        return False
    if not is_view_op(wid, verdict_action):
        return True
    # …and a words-only lens (`output.answer`) where the verdict names one that changes the screen (full26 E2).
    try:
        from widgets import effects as _fx
        return (_fx.carries(wid, model_action, _fx.OUTPUT_ANSWER)
                and not _fx.carries(wid, verdict_action, _fx.OUTPUT_ANSWER))
    except Exception:  # noqa: BLE001
        return False


def _card_revision(wid: str) -> int:
    try:
        from widgets import store as _wstore
        return _wstore.revision(wid)
    except Exception:  # noqa: BLE001
        return 0


def remember_refusal(wid: str, action: str, payload: dict | None) -> None:
    import time as _t
    w = str(wid or "").strip().lower()
    _REFUSED["v"] = (w, str(action or "").strip(), dict(payload or {}), _t.time(), _card_revision(w))


def is_identical_retry_of_refused(wid: str, action: str, payload: dict | None, *, now: float | None = None) -> bool:
    """…and it can only fail again while the card holds what it held: once its data changed since the refusal,
    the same call is a new question (demo pass 31, E2→E3: the mail's history landed 3 s after the refusal)."""
    import time as _t
    last = _REFUSED["v"]
    if not last:
        return False
    l_wid, l_action, l_payload, l_ts, l_rev = last
    if l_wid != str(wid or "").strip().lower() or l_action != str(action or "").strip() or l_payload != dict(payload or {}):
        return False
    if _card_revision(l_wid) != l_rev:
        return False
    return ((now if now is not None else _t.time()) - l_ts) < _REFUSED_S


def is_context_bleed(last, wid: str, action: str, payload: dict | None, said: str, *, now: float | None = None,
                     brief=None) -> bool:
    """V2-038 anti-drag: a MUTATION identical to the last (<120 s) whose content the turn does not name is a drag.
    Hatches: words name the payload, or a replay order (V2-650). V2-717: a lens is never a drag (c502d3ff)."""
    import time as _t
    if not last:
        return False
    try:
        l_wid, l_action, l_payload, l_ts = last
    except (TypeError, ValueError):
        return False
    if l_wid != wid or l_action != action or l_payload != (payload or {}):
        return False
    if ((now if now is not None else _t.time()) - l_ts) >= 120:
        return False
    if is_view_op(wid, action) or is_step_op(wid, action):     # a lens writes nothing; a step is another step
        return False
    if word_overlap(" ".join(str(v) for v in (payload or {}).values()), said) > 0:
        return False
    try:
        from nucleo.flash import canvas_license as _lic
        if _lic.replay_license(wid, action, said):
            return False
    except Exception:  # noqa: BLE001
        pass
    from nucleo.flash import redo_license as _redo_lic     # V2-791: a REDO is not a drag
    return not _redo_lic.licensed(last, wid, said, brief=brief)
