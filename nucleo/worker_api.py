"""nucleo/worker_api.py — REQUEST/RESPONSE blueprint for Brain Workers (V2-038, §v2·B + §v3·I/J/K).

A worker (subprocess, any backend) talks to the live server over HTTP to REQUEST things that only the host/
FlashBrain can do or that require a response:
  · `ask_user`  — ask the operator and WAIT ("¿enduro o cross?").
  · `use_tool`  — use a FlashBrain TOOL (web_search today; FILTERED catalog §v3·J) → the brain executes it and
                  returns the result (the operator asked: "the brain executes searches and returns them to the worker").
  · `read_widget`/`show_widget`/`close_widget` — read/show/close a canvas widget.
  · `push_channel` — push to an external channel (CONFIRM + scan_outbound).
  · `spawn` — chain another Brain Worker (within quota/depth limits).

ONE endpoint (`ask` = `act action=ask_user`), ALLOW/CONFIRM/DENY policy evaluated HERE (server, not in the
worker prompt), CONFIRM = an auto-generated `ask_user` (§v3·K), idempotent re-poll (§v3·I), and **piggyback**: every
response carries the pending FlashBrain injections for that task (§v3·H). Per-task token auth (§v2·D).
"""
from __future__ import annotations

import asyncio
import secrets
import time

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()


# ── per-action policy (§v3·J) ───────────────────────────────────────────────────────────────────────────────
# ALLOW/CONFIRM/DENY vocab, the prestable/deny tool sets, _KNOWN_ACTS, deny_reason(), classify_act() and
# _confirm_question() moved to nucleo/worker_policy.py (2026-08-17 modularization pass) — pure decision
# logic, no I/O. Re-exported here so every existing call site (worker_api.classify_act(...), direct
# `from nucleo.worker_api import deny_reason` in tests, etc.) keeps working unchanged.
from nucleo.worker_policy import (  # noqa: F401 — re-export
    ALLOW, CONFIRM, DENY, _PRESTABLE_TOOLS, _DENY_TOOLS, _KNOWN_ACTS, deny_reason, classify_act,
    _confirm_question,
)
_MAX_DEPTH = 2



# ── in-flight request registry (corr_id → state) ────────────────────────────────────────────────────────────
_ACTS: dict[str, dict] = {}

from nucleo.runtime_ids import next_seq as _next_seq


def _new_corr(task_id: str, action: str) -> str:
    """UNPREDICTABLE corr_id: re-polling (`GET /act/{corr_id}`) carries no token — the corr IS the capability. A
    sequential one would be guessable (read the operator's response + steal the injection piggyback, §v2·D)."""
    return f"{task_id}:{action}:{_next_seq('worker_api.corr')}:{secrets.token_urlsafe(8)}"


def _piggyback(task_id: str) -> list[str]:
    """Pending FlashBrain injections for this worker (§v3·H) — served in ANY bridge response."""
    try:
        from nucleo import dispatch
        return dispatch.take_pending_injects(task_id)
    except Exception:
        return []


def _verify(task_id: str, token: str):
    """Return the SessionRecord if the token matches; None otherwise (per-task auth, §v2·D)."""
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is None:
            return None
        if dispatch.rec_token(rec) != (token or ""):
            return None
        return rec
    except Exception:
        return None


# ── immediate execution of ALLOW actions ─────────────────────────────────────────────────────────────────
#: How many reminders ONE background task may schedule. This is the capability filter, not a decorative number: without
#: a cap, a looping worker fills the operator's agenda and each entry later triggers a turn.
_SCHEDULE_CAP = 3

#: The forms the parser REALLY accepts, in one sentence. Written here once because it appears in all three errors, and
#: because a list of examples that do not parse is worse than none: it sends the worker to retry the same thing.
_CUANDO_VALE = ('Vale «mañana a las 9», «el miércoles a las 18:00», un día del mes («el 3 a las 10»), '
                '«every 30m» para algo que se repite, o un cron de 5 campos «0 9 * * 3».')


def _safe_reminder_prompt(text: str) -> str:
    """Normalize a cron prompt to the REMINDER form — same rule as the other two gates (V2-214).

    Safeguard: this action already works today, and losing a reminder the worker was able to create because of an import
    peor que dejar pasar una redacción cruda.
    """
    try:
        from nucleo.flash.router_guards import safe_reminder_prompt
        return safe_reminder_prompt(text)
    except Exception:  # noqa: BLE001
        return text


async def _exec_allow(action: str, payload: dict, rec) -> dict:
    payload = payload or {}
    if action == "use_tool" and payload.get("tool") == "web_search":
        q = (payload.get("args") or {}).get("query") or payload.get("query") or ""
        try:
            from nucleo import websearch
            res = await asyncio.to_thread(websearch.search, str(q))
            # V2-236: and what the search brings goes INTO THE CONVERSATION immediately, not when the worker delivers
            # it — which failed to happen in 5 of 8 measured sessions. Same remedy V2-223 gave to what the browser
            # extracts through the other gate: this is OUR search, lent to the worker.
            try:
                from nucleo.workers import findings
                findings.hand_web_finding(getattr(rec, "task_id", ""), findings.render_search(res),
                                          getattr(rec, "goal", ""))
                # V2-320 — …and INTO THE SHEET, where the operator looks. A worker that solves by searching (without
                # a browser) ALWAYS left the sheet empty: the return only had a path to the note. Same gate as
                # the browser (V2-257) and the same rows carried by the note.
                findings.hand_search_rows(rec, res)
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "result": res}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"web_search falló: {e}"}
    if action == "schedule":
        # V2-249 — the SCHEDULED reminder must really exist, or it must not be claimed. A worker told
        # «remind him on Wednesday» could not do it (the capability did not exist) and durably wrote in memory
        # that it had scheduled it. The harness set the bar: **the entry must exist, or the pill must not say
        # «scheduled»**. This does the former.
        when = str(payload.get("when") or payload.get("schedule") or "").strip()
        what = str(payload.get("prompt") or payload.get("text") or payload.get("what") or "").strip()
        tid = str(getattr(rec, "task_id", "") or "")
        if not what:
            return {"ok": False, "error": "falta `prompt`: qué tiene que decir o hacer zaelar cuando llegue el "
                                          "momento, escrito como se lo dirías a él."}
        if not when:
            return {"ok": False, "error": "falta `when`: cuándo. " + _CUANDO_VALE}
        try:
            from nucleo import scheduler
            # TWO parsers, in this order: `parse_schedule` understands machine forms («every 30m», a 5-field cron,
            # `YYYY-MM-DD HH:MM`) and `parse_when` translates spoken forms («mañana a las 9», «el miércoles a las
            # 18:00»). The worker writes as it speaks, so without the second almost all of its input would be rejected;
            # without the first, recurrence would be lost.
            spec = when if scheduler.parse_schedule(when) else (scheduler.parse_when(when) or "")
            if not spec:
                # `parse_when` deliberately returns "" for ambiguous input («esta tarde», «pronto»): a reminder set
                # for a guessed date is worse than none, because the operator is left believing it is scheduled.
                return {"ok": False, "error": f"«{when}» no me dice un momento exacto y no lo adivino: un aviso "
                                              f"sobre una fecha inventada es peor que ninguno. " + _CUANDO_VALE}
            # THE CAP, which is this capability's filter (same pattern as the `spawn` quota): a looping worker
            # cannot fill the operator's agenda. It is counted over LIVE tasks and by attribution, so no new state
            # is needed and no stale number survives a restart.
            mias = [j for j in scheduler.list_jobs() if f"[worker:{tid}]" in str(j.get("name") or "")]
            if len(mias) >= _SCHEDULE_CAP:
                return {"ok": False, "error": f"ya has programado {len(mias)} avisos en esta tarea, que es el "
                                              f"tope. Si necesitas otro, cancela uno o dilo en tu entrega."}
            name = f"{(payload.get('name') or what)[:80]} [worker:{tid}]"
            # V2-480 — THE THIRD GATE. `safe_reminder_prompt` has existed since V2-214 and its docstring says «so
            # that the TWO gates to the scheduler say the same thing»; this action is the THIRD, born later
            # (V2-249), and never called it. A cron's reader is the AGENT at another time, so leaving the operator's
            # words asks it to TAKE NOTES — the loop this whole area exists to close.
            what = _safe_reminder_prompt(what)
            out = await asyncio.to_thread(scheduler.create, what, spec, name)
            if not out.get("ok"):
                # It knows the form; let it say so (same contract as V2-203).
                return {"ok": False, "error": f"{out.get('error') or 'no se pudo programar'}. " + _CUANDO_VALE}
                # V2-249 — AND MAKE IT VISIBLE. A reminder due in three days was created by a background task that
                # no longer exists by then: without a row, the operator encounters it without knowing where it came
                # from. The row carries the REAL ID, which allows a pill to be checked against the scheduler —
                # memoria-dev noted that nothing currently verifies a system claim about its own effects, and this
                # is the half that the action executor can provide: leave the proof.
            try:
                from voice.observer import emit
                emit("task", "⏰ aviso programado",
                     text=f"{out.get('display') or when} — {what[:120]}",
                     extra={"id": tid, "src": f"worker:{tid}", "cron_id": out.get("id"),
                            "when": out.get("display") or when})
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "result": {"id": out.get("id"), "cuando": out.get("display") or when,
                                           "que": what,
                                           "ref": f"cron:{out.get('id')}"}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"no pude programarlo: {e}"}
    if action == "read_widget":
        wid = str(payload.get("id") or payload.get("widget_id") or "")
        try:
            from widgets import runtime
            from widgets.server_api import MISSING, run_widget_hook
            man = runtime.get(wid)
            if not man:
                # …and before saying it does not exist, ASK about the name the rest of the system already knows:
                # the registry contains the identity of all 26 (id, name, and alias), and this bridge did not consult it.
                from widgets import naming as _nm
                _id, _varios = _nm.resolve(wid)
                if _id:
                    wid, man = _id, runtime.get(_id)
                if not man:
                    return {"ok": False, "error": _nm.not_found(wid, _varios)}

            def _call(view_data):
                try:
                    return view_data(q="")
                except TypeError:            # old widgets without a query argument
                    return view_data()

            # the widget DATA (§7.3: view_data), off-loop and with a timeout — not just the manifest.
            data = await run_widget_hook(wid, "view_data", _call)
            return {"ok": True, "result": {"manifest": man,
                                           "data": None if data is MISSING else data}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"read_widget falló: {e}"}
    if action in ("show_widget", "close_widget"):
        wid = payload.get("id") or payload.get("widget_id") or ""
        # V2-359 — «show results» from a worker means MY results. The worker knows the widget's NAME, never its
        # errand instance, and passing the bare id through opened the BASE card ON TOP of the errand's own sheet
        # — the intermittent «TARJETA FANTASMA» the round reports keep naming (bilbao 08:38 and coche 08:03:
        # base `results` beside its instances, empty; V2-351 swept the RESTORE-time fossils but this opener is
        # live, mid-round). Same decision the voice channel took in 246007a («enséñamelo» resolves to the
        # ERRAND's sheet): when this worker's errand has a sheet, the bare `results` resolves to it. A worker
        # with no sheet keeps the base — the default sheet IS its sheet.
        try:
            if str(wid).strip().lower() == "results":
                from nucleo import sheets as _sh
                _sid = _sh.sheet_of(rec)
                if _sid:
                    from widgets.results import data as _rd
                    wid = _rd.instance_id(_sid)
        except Exception:
            pass
        try:
            from voice.observer import emit
            _src = f"worker:{getattr(rec, 'task_id', '')}"        # V2-039: provenance — Brain Worker command
            extra = {"id": str(wid), "src": _src} if action == "show_widget" else {"src": _src}
            _tid = getattr(rec, "trace_id", "")                   # V2-044: HTTP handler without context → session trace
            if _tid:
                extra["trace"] = _tid
                extra["span"] = f"worker:{getattr(rec, 'task_id', '')}"
            emit("widget", "show" if action == "show_widget" else "close", extra=extra)
            return {"ok": True, "result": {"widget": wid}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    if action == "widget_data":
        # V2-061 worker→widget bridge: applies the data-op through the SAME path as the FlashBrain's [[widget.data]]
        # tag (widgets.brain_action → the widget's apply_action, off-loop, isolated, never crashes). The PROVENANCE
        # is sealed as worker:<id> (V2-039) so the widget/data event is not attributed to "user".
        wid = str(payload.get("widget_id") or payload.get("id") or "").strip().lower()
        act = str(payload.get("action") or "").strip()
        data_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if not wid or not act:
            return {"ok": False, "error": "widget_data requiere widget_id y action"}
        # V2-259 — WHICH SHEET. The worker prompt says «deliver to the `results` sheet» (V2-257), and with
        # instances that bare name stops being an address: it would write to the box nobody looks at while the
        # operator has THEIR assignment's box in front of them. The BRIDGE resolves it, deliberately, not the worker:
        # a worker should not need to know instance IDs, and asking for them would create a new way to make mistakes.
        # An explicit `sheet` is respected in case it is ever needed, but nobody tells it about this.
        if wid == "results" and not str(data_payload.get("sheet") or "").strip():
            try:
                from nucleo.dispatch import sheet_of as _sheet_of_rec
                _own = _sheet_of_rec(rec)
            except Exception:  # noqa: BLE001
                _own = ""
            if _own:
                data_payload = {**data_payload, "sheet": _own}
        try:
            from widgets import runtime
            if runtime.get(wid) is None:
                from widgets import naming as _nm
                _id, _varios = _nm.resolve(wid)
                if _id and runtime.get(_id) is not None:
                    wid = _id
                else:
                    return {"ok": False, "error": _nm.not_found(wid, _varios)}
            try:
                from widgets import provenance as _prov
                _prov.note(wid, f"worker:{getattr(rec, 'task_id', '')}")
            except Exception:
                pass
            from widgets.server_api import brain_action
            res = await brain_action(wid, act, data_payload)
            if isinstance(res, dict) and res.get("error"):
                return {"ok": False, "error": str(res.get("error"))}
            return {"ok": True, "result": {"widget": wid, "action": act, "data": res}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"widget_data falló: {e}"}
    if action == "spawn":
        return await _spawn_child(payload, rec)
    return {"ok": False, "error": "acción ALLOW no ejecutable"}


async def _spawn_child(payload: dict, rec) -> dict:
    """Chain another Brain Worker within quota/depth limits (§v3·J: DENY when exceeded)."""
    depth = int(getattr(rec, "depth", 0) or 0)
    if depth + 1 > _MAX_DEPTH:
        return {"ok": False, "error": "límite de profundidad de cadena alcanzado"}
    req = (payload or {}).get("request") or ""
    if not req:
        return {"ok": False, "error": "spawn sin request"}
    try:
        from nucleo.flash import escalate
        cid = escalate.escalate_to_slowbrain(str(req), context={
            "src": "worker", "kind": (payload.get("kind") or "generic"),
            "parent_task_id": rec.task_id, "depth": depth + 1})
        return {"ok": True, "result": {"child_id": cid}}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"spawn falló: {e}"}


def purge_task(task_id: str) -> int:
    """§v3·L: when a session dies/is killed, its PENDING requests are purged — the loop must not recount a dead
    session's question. Answered requests are retained (a late `hbask wait` from the still-live group gets a clean 404).
    Called by dispatch (cancel_session / end of session)."""
    n = 0
    for corr, e in list(_ACTS.items()):
        if e.get("task_id") == str(task_id) and e.get("state") == "pending":
            _ACTS.pop(corr, None)
            n += 1
    return n


_ANSWERED_TTL_S = 600.0


def _prune() -> None:
    """Prune old ANSWERED entries (the worker has claimed them or died) — the registry never grows without limit."""
    cut = time.time() - _ANSWERED_TTL_S
    for corr, e in list(_ACTS.items()):
        if e.get("state") == "answered" and float(e.get("created") or 0) < cut:
            _ACTS.pop(corr, None)


def _register_ask(rec, question: str, action: str = "ask_user", retained: dict | None = None) -> str:
    """Park a pending question (ask_user or an act's CONFIRM, §v3·K) → waiting_on=user + bus worker.ask."""
    _prune()
    corr = _new_corr(rec.task_id, action)
    _ACTS[corr] = {"corr_id": corr, "task_id": rec.task_id, "action": action, "question": question,
                   "state": "pending", "answer": "", "result": None, "retained": retained or {},
                   "created": time.time()}
    rec.waiting_on = "user"
    rec.ask = question
    rec.ask_corr = corr
    try:
        import bus
        bus.emit_sync("worker.ask", {"id": rec.task_id, "question": question, "corr_id": corr})
    except Exception:
        pass
    return corr


# ── endpoints ────────────────────────────────────────────────────────────────────────────────────────────
@router.post("/api/worker/act")
async def worker_act(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     action: str = Body(..., embed=True), payload: dict = Body(default={}, embed=True)):
    """The worker requests an action. Verify token → policy → execute (immediate ALLOW), park (ask/CONFIRM), or
    deny. Always carries the injection piggyback."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)

    pol = classify_act(action, payload)
    if pol == DENY:
        return JSONResponse({"ok": False, "denied": True,
                             "error": deny_reason(action, payload), "injections": inj})

    if action == "ask_user":
        q = (payload or {}).get("question") or (payload or {}).get("text") or ""
        corr = _register_ask(rec, str(q))
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    if pol == CONFIRM:
        # §v3·K: an irreversible act becomes an auto-generated ask_user with the RETAINED action.
        q = _confirm_question(action, payload)
        corr = _register_ask(rec, q, action=action, retained={"action": action, "payload": payload})
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    # ALLOW inmediato
    res = await _exec_allow(action, payload or {}, rec)
    res["injections"] = inj
    return JSONResponse(res)


@router.post("/api/worker/say")
async def worker_say(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     text: str = Body("", embed=True)):
    """The worker SAYS something to the user (EXPLICIT say, §v2·E·Q3) — recounted by voice+UI with attribution. Piggyback."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)
    msg = (text or "").strip()
    if msg:
        try:
            import bus
            bus.emit_sync("worker.say", {"id": task_id, "text": msg[:400]})
        except Exception:
            pass
        try:
            from voice import proactive
            await proactive.notify("zaelar", msg, speak=True)
        except Exception:
            pass
    return JSONResponse({"ok": True, "injections": inj})


@router.get("/api/worker/act/{corr_id}")
async def worker_act_poll(corr_id: str):
    """Idempotent re-poll (§v3·I): state of a parked request. The response is stored until claimed."""
    e = _ACTS.get(corr_id)
    tid = (e or {}).get("task_id", "")
    inj = _piggyback(tid) if tid else []
    if not e:
        return JSONResponse({"ok": False, "error": "corr_id desconocido", "injections": inj}, status_code=404)
    if e["state"] == "answered":
        return JSONResponse({"ok": True, "status": "answered", "answer": e.get("answer", ""),
                             "result": e.get("result"), "injections": inj})
    return JSONResponse({"ok": True, "status": "pending", "injections": inj})




# ── ask resolution (called by FlashBrain/provider when the operator responds) ──────────────────────────────
def has_pending_ask() -> bool:
    return any(e["state"] == "pending" for e in _ACTS.values())


def pending_asks() -> list[dict]:
    """Pending questions (for the supervisor loop: recount them by voice, one at a time, FIFO)."""
    out = [e for e in _ACTS.values() if e["state"] == "pending"]
    out.sort(key=lambda e: e["created"])
    return [{"corr_id": e["corr_id"], "task_id": e["task_id"], "question": e["question"],
             "action": e["action"]} for e in out]


def active_ask() -> dict | None:
    """The OLDEST pending ask (the 'active' one being recounted, §v3·M/Q5)."""
    p = pending_asks()
    return p[0] if p else None


async def answer(corr_id: str, text: str) -> bool:
    """Resolve an ask by corr_id: store the response and, if it was an act CONFIRM, EXECUTE the retained action
    (§v3·K). Clear waiting_on on the record. Return True if something was resolved."""
    e = _ACTS.get(corr_id)
    if not e or e["state"] != "pending":
        return False
    e["answer"] = text or ""
    e["state"] = "answered"
    # Retained CONFIRM: "sí" → execute the action; anything else → no.
    retained = e.get("retained") or {}
    if retained.get("action") and _is_yes(text):
        try:
            from nucleo import dispatch
            rec = dispatch.get_record(e["task_id"])
            if rec is not None:
                e["result"] = await _exec_allow(retained["action"], retained.get("payload") or {}, rec)
        except Exception:
            pass
    _clear_waiting(e["task_id"], corr_id)
    return True


async def answer_active(text: str) -> bool:
    """Resolve the ACTIVE (oldest) ask — deterministic path when the operator responds by voice (§v3·M)."""
    a = active_ask()
    if not a:
        return False
    return await answer(a["corr_id"], text)


def answer_active_soon(text: str) -> bool:
    """Fire-and-forget marshalled to the server loop (§v3·D/O): resolve the active ask. Called by FlashBrain from
    the job thread. Return True if there WAS an ask to answer (so voice can confirm)."""
    if not has_pending_ask():
        return False
    try:
        import asyncio

        from nucleo import dispatch
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(answer_active(text), loop)
        else:
            asyncio.ensure_future(answer_active(text))
        return True
    except Exception:
        return False


def match_by_options(text: str) -> str | None:
    """§v3·M/Q5: if the short response clearly matches the `options` of ANY pending ask, return its corr_id
    (to route to that one, not the active one). Conservative placeholder: without declared options, None."""
    return None


def _clear_waiting(task_id: str, corr_id: str) -> None:
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is not None and getattr(rec, "ask_corr", "") == corr_id:
            rec.waiting_on = ""
            rec.ask = ""
            rec.ask_corr = ""
    except Exception:
        pass


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(w in t for w in ("sí", "si", "vale", "adelante", "hazlo", "ok", "yes", "dale", "confirmo"))
