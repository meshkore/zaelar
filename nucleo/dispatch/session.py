"""One Brain Worker SESSION, from its gate to its delivery (V2-778 F1, 2026-10-01).

Moved out of `nucleo/dispatch.py` (1,586 lines), where `_run_session` was 387 lines of a file over its ceiling. The
code is the SAME; every name it read from the dispatcher (its registry, the pool, the prompt composers, the resume
helpers…) is read through the module (`_d.<name>`), so a patch on `nucleo.dispatch` still governs it, and
`dispatch._run_session` stays as a delegate — the escalation listener and the tests call it by that name.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

from nucleo import dispatch as _d
from nucleo.dispatch import confirm as _dconf
from nucleo.workers import reach_gap as _rg

if TYPE_CHECKING:
    from nucleo.dispatch import Task


async def _run_session(task: "Task") -> None:
    """Crea and conduce UNA session bajo the pool. Never lanza (corre como task suelta)."""
    from nucleo import danger
    from nucleo.acts import errand as escalate

    key = str(task.id)
    req = (task.request or "").strip()

    # TRAZABILIDAD (V2-044): adopta the trace of the frase that origino the escalada (viajo in task.context because the
    # bus no copia contexto). span=worker:<id> → TODOS the emits of the ciclo (fases, chips, entrega, notify) quedan
    # encadenados a esa frase in the arbol of Trazas.
    try:
        from voice import trace as _trace
        _rec0 = _d._SESSIONS.get(key)
        _tid0 = (task.context or {}).get("trace") or (getattr(_rec0, "trace_id", "") if _rec0 else "")
        if _tid0:
            _trace.adopt(str(_tid0), span=f"worker:{key}")
            if _rec0 is not None and not _rec0.trace_id:
                _rec0.trace_id = str(_tid0)
    except Exception:
        pass
    kind = (task.kind or "generic").strip() or "generic"
    if kind == "generic":
        kind = _d._classify_kind(req)
    trusted = bool(task.trusted)

    # CONFIRM-GATE (V2-007): the ONE act-or-ask rule over the errand's class — the brief's `errand_class` carried in its
    # context, the money vocabulary only when there is none (refactor2710-06 T-03) — before anything starts.
    from nucleo.acts import errand as _errand
    _cls = _errand.class_of(task.context.get("errand_class"), req)
    if trusted and _errand.asks_first(_cls, confirmed=bool(task.context.get("confirmed"))):
        _d.logger.info(f"dispatch: tarea {key} PARA por confirm-gate: {req[:80]}")
        rec = _d._SESSIONS.get(key)
        if rec:
            rec.status = "done"
            rec.result_summary = danger.confirm_question(req)
            await _d._deliver_confirm(rec)
            _d._SESSIONS.pop(key, None)
            # The question is REMEMBERED (V2-126): the gate used to speak it and drop the record, nobody ever set
            # `context["confirmed"]`, so a yes had nothing to return to and the next turn narrated work that did
            # not exist (`cancel-subscription-before-charge`, `pay-known-bill`). …and with its SHEET, already on
            # screen, so the yes returns to it (V2-508).
            _d.remember_confirm(key, req, task, sheet=_d.sheet_of(rec))
            _d._task_row("withdrawn", rec)
            _d.sync_state()
        return

    # THE GATE FOR TOUCHING A CARD OF HIS (V2-757): a card of his is not built or rewritten unless he said so, knowing
    # he said it (session f84f91ef: a design brief dictated to ANOTHER conversation started a worker rewriting his
    # YouTube card). Here because `_run_session` is the ONE door that starts a worker, with `kind == "code"` already
    # decided by `errand_kind`. The cluster dev worker (V2-076) is out of scope: it brings its own repo and licence.
    if (kind == "code" and not bool(task.context.get("confirmed"))
            and not _d._dev_worker_params(task.context)):
        from nucleo.request import kind as _ek_gate
        _d.logger.info(f"dispatch: task {key} STOPPED by the widget confirm-gate: {req[:80]}")
        rec = _d._SESSIONS.get(key)
        if rec:
            rec.status = "done"
            rec.result_summary = _ek_gate.code_change_question(req)
            await _d._deliver_confirm(rec)
            _d._SESSIONS.pop(key, None)
            _d.remember_code_change(key, req, task, sheet=_d.sheet_of(rec))
            _d._task_row("withdrawn", rec)
            _d.sync_state()
        return

    if await _dconf.unlicensed_gate(task, key, req):   # V2-812 T-03: a line that was not a request asks first
        return

    rec = _d._SESSIONS.get(key)
    if rec is None:
        return
    rec.kind = kind
    rec.label = _d._default_label(kind, req)
    _d.sync_state()

    # THE WHOLE CHAIN ASLEEP starts nothing (V2-314): `providers.pick()` is None both for an EMPTY chain (self-host:
    # the local licence, fail-open) and an all-in-cooldown one; `exhausted_until()` tells the two apart.
    try:
        from nucleo.workers import providers as _prov, quota_wait as _qwait
        _sleep_reason = _prov.exhausted_reason()
    except Exception:  # noqa: BLE001
        _sleep_reason = ""
    if _sleep_reason:
        _d.logger.warning(f"dispatch: tarea {key} NO se lanza — cadena de proveedores agotada")
        try:
            from voice.observer import emit
            # `provider_asleep` and not a plain `end`: the round did not fail, it never started. Observability and
            # the harness both need to tell «we tried and it broke» from «we knew it was pointless», or an
            # exhausted quota keeps being scored as a broken product.
            emit("task", "provider_asleep", role="system", text=req[:120],
                 extra={"id": key, "ok": False, "until": _prov.exhausted_until(),
                        "reason": "todos los escalones del worker en cooldown: lanzar es morir"})
        except Exception:
            pass
        rec.status = "done"
        rec.ok = False
        rec.result_summary = _qwait.parked_summary(req, task.context, _sleep_reason)   # parked → resumed at reset
        await _qwait.tell(rec, _d._deliver_confirm)   # the confirm-gate's one-liner path, said once per refusal
        _d._SESSIONS.pop(key, None)
        _d._task_row("ended_early", rec, state="failed")
        _d.sync_state()
        return

    async with _a_slot(_d, key, rec):
        if rec.status == "cancelled":         # cancelada mientras esperaba el pool (its surface: `_a_slot`)
            _d._SESSIONS.pop(key, None)
            _d._task_row("ended_early", rec, state="cancelled")
            return
        ctx = await _d._compose_context(req, kind)
        # V2-778 F1 — building what the session runs with lives in `nucleo/dispatch/session_steps.py`.
        _blk = await _dss.build_what_it_runs_with(
            ctx=ctx,
            key=key,
            kind=kind,
            rec=rec,
            req=req,
            task=task,
            trusted=trusted,
        )
        if '_brief_bg' in _blk:
            _brief_bg = _blk['_brief_bg']
        if '_dev' in _blk:
            _dev = _blk['_dev']
        if '_dev_settings_path' in _blk:
            _dev_settings_path = _blk['_dev_settings_path']
        if '_wd' in _blk:
            _wd = _blk['_wd']
        if 'brief' in _blk:
            brief = _blk['brief']
        if 'nav_tid' in _blk:
            nav_tid = _blk['nav_tid']
        if 'resume' in _blk:
            resume = _blk['resume']
        if 'session' in _blk:
            session = _blk['session']
        # V2-825 F6 — the worker's FIRST step: a declared window older than the resource's reach is a capability gap.
        if (_gap := _rg.gap(_rg.window_of(brief, task.context))):
            return await _rg.end(_d, key, rec, _gap)
        if _dev:
            prompt = _d._dev_prompt(req, _dev["repo"])
        elif kind == "web" and trusted:
            # V2-289 — the step 1 of the metodo le says that the VISIÓN es su camino PRINCIPAL, and with a escalon that
            # no reads imagenes eso es a orden imposible: the descubre haciendo `Read` of a PNG of medio mega and
            # narrando the failure. Who can ver it resuelve the catalogo of escalones, that es the only that sabe
            # who sirve the session (`providers.worker_sees`, fail-open a SÍ ve).
            prompt = _d._web_prompt(req, ctx, brief, vision=_d._worker_sees())
        else:
            prompt = _d._build_prompt(req, ctx, trusted, brief)
        # V2-644 (a REPORT flips the delivery contract) + V2-661 (where the operator's FILES live): the blocks
        # a trusted worker gets after the method block, composed in one place.
        if trusted and not _dev:
            from nucleo.dispatch_prompts import trusted_blocks
            prompt += trusted_blocks(getattr(rec, "surface", ""))
        if resume and (kind == "web" and trusted):
            prompt = ("REANUDAS una gestión que YA empezaste (no arranques de cero): la pestaña sigue donde la "
                      "dejaste y los datos que ya reuniste están en memoria (consúltalos con cli.mem recall). Haz "
                      "`look` PRIMERO para ver dónde te quedaste y CONTINÚA desde ahí hasta terminar.\n\n") + prompt
        if _brief_bg is not None:
            # V2-301 — the compositor continues pensando: the worker starts YA and the address le arrives inyectada.
            prompt += ("\n\nNOTA (dirección en camino): la DIRECCIÓN detallada de esta investigación — criterios "
                       "duros y blandos, amplitud mínima y baremo — se está componiendo y te llegará como "
                       "instrucción nueva en un momento. NO la esperes parado: haz ya los primeros pasos (PASO 0, "
                       "abrir el sitio, la primera búsqueda) y aplícala en cuanto llegue.")
            _d._attach_brief_followup(_brief_bg, key=key, rec=rec, req=req, kind0=kind)
        # V2-778 F1 — running the session to its delivery lives in `nucleo/dispatch/session_steps.py`.
        _blk = await _dss.run_it_to_its_delivery(
            _dev=_dev,
            _dev_settings_path=_dev_settings_path,
            _wd=_wd,
            brief=brief,
            escalate=escalate,
            key=key,
            kind=kind,
            nav_tid=nav_tid,
            prompt=prompt,
            rec=rec,
            req=req,
            resume=resume,
            session=session,
            trusted=trusted,
        )


from nucleo.dispatch import session_steps as _dss  # noqa: E402 — V2-778 F1, reads this module back


@contextlib.asynccontextmanager
async def _a_slot(_d, key, rec):
    """The worker pool, entered the way the operator should see it: a commission that waits says behind what, and
    its silence starts when it RUNS, never while it waited for a slot (the loop's stuck clock reads it)."""
    _say_queued_behind(_d, key)
    try:
        await _d._pool().acquire()
    except asyncio.CancelledError:          # stopped while it waited: it never ran, so its finally never will
        _settle_unrun(_d, rec, key)
        raise
    try:
        rec.last_event_at = time.time()
        if getattr(rec, "status", "") == "cancelled":
            _settle_unrun(_d, rec, key)     # stopped while it waited, noticed only now: same leftovers
        yield
    finally:
        _d._pool().release()


def _settle_unrun(_d, rec, key) -> None:
    """A commission stopped before it ever RAN leaves no «Working…» behind (demo 2026-10-22).

    The trip plan was cancelled while queued; the cancel came through `asyncio` at the pool's door, outside the
    session's `finally` — the only place a sheet is closed — so its card said «Working…» for good, on top of the
    document he was reading. The sheet's loader stops as at any end, and a sheet with nothing in it leaves the screen;
    one that holds rows stays, it is his. Never raises."""
    try:
        surf = getattr(rec, "surface", "")
        if _d.surfaces.opens_sheet(surf):
            _d._sheet_close(rec)
            from widgets.results import data as _sheet
            sid = _d.sheet_of(rec)
            if sid and not (_sheet.view_data(sid).get("items") or []):
                from nucleo.acts import canvas
                canvas.apply("close", _sheet.instance_id(sid), src=f"worker:{key}")
        elif _d.surfaces.opens_doc(surf):
            _d._docsheet.doc_close(rec)
    except Exception as e:  # noqa: BLE001
        _d.logger.debug(f"dispatch: the unrun {key} left its surface as it was: {e}")


def _say_queued_behind(_d, key) -> None:
    """A commission that has to WAIT for a slot says so, and behind what (demo 2026-10-22).

    Two run at a time (`code_agent.max_parallel`); the trip plan sat «queued» for four minutes behind a 14-minute
    monitor search and the Bitcoin summary, the agent told him it was «stuck», and «restarting» it only cancelled the
    one in the queue. The phase now names the work it waits behind, so the row, the prompt and the agent all read the
    same fact. Never raises: a phase that cannot be written leaves the plain «queued»."""
    try:
        if not _d._pool().locked():
            return
        from nucleo.workers import progress as _progress, reports as _reports
        ahead = [str(x.get("title") or x.get("goal") or "")[:60] for x in _d.active_sessions()
                 if str(x.get("id")) != str(key) and x.get("status") == "running"]
        ahead = [a for a in ahead if a]
        if ahead:
            _reports.session_phase(key, _progress.say("queued_behind", "queued — waiting for a free slot behind: {names}",
                                                  names=" · ".join(ahead)))
    except Exception as e:  # noqa: BLE001
        _d.logger.debug(f"dispatch: queued phase not written for {key}: {e}")
