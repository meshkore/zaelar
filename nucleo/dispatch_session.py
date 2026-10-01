"""One Brain Worker SESSION, from its gate to its delivery (V2-778 F1, 2026-10-01).

Moved out of `nucleo/dispatch.py` (1,586 lines), where `_run_session` was 387 lines of a file over its ceiling. The
code is the SAME; every name it read from the dispatcher (its registry, the pool, the prompt composers, the resume
helpers…) is read through the module (`_d.<name>`), so a patch on `nucleo.dispatch` still governs it, and
`dispatch._run_session` stays as a delegate — the escalation listener and the tests call it by that name.
"""
from __future__ import annotations

from nucleo import dispatch as _d


async def _run_session(task: "Task") -> None:
    """Crea and conduce UNA session bajo the pool. Never lanza (corre como task suelta)."""
    from nucleo import danger
    from nucleo.flash import escalate

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

    # CONFIRM-GATE of irreversibles (V2-007) — before of start nothing.
    if trusted and danger.is_dangerous(req) and not bool(task.context.get("confirmed")):
        _d.logger.info(f"dispatch: tarea {key} PARA por confirm-gate: {req[:80]}")
        rec = _d._SESSIONS.get(key)
        if rec:
            rec.status = "done"
            rec.result_summary = danger.confirm_question(req)
            await _d._deliver_confirm(rec)
            _d._SESSIONS.pop(key, None)
            # La question is RECUERDA (V2-126). Hasta here the gate era a callejon without salida: hablaba the
            # question by the rail proactivo, tiraba the record, and nadie ponia never `context["confirmed"]`
            # — a `si` of the operator no tenia a what volver. Peor: the task desaparecia of `pending_summaries`,
            # so that the turn siguiente NO veia nothing pending and volvia a narrar work that no existia.
            # Medido in `cancel-subscription-before-charge` and in `pay-known-bill` (three tasks, the three
            # paradas by the gate, ninguna contada al operator).
            # …with su HOJA: already esta abierta in pantalla and the «si» has that volver a ELLA (V2-508).
            _d.remember_confirm(key, req, task, sheet=_d.sheet_of(rec))
            _d._task_row("withdrawn", rec)
            _d.sync_state()
        return

    # THE GATE FOR TOUCHING A CARD OF HIS (V2-757, 2026-09-23). A card of his is not built and not
    # rewritten without him having said so, out loud, knowing he said it.
    #
    # MEASURED LIVE (session f84f91ef). With the mic open, the operator dictated a several-minute design
    # brief to ANOTHER conversation («hace el header ese más bonito», «todos los gráficos a la misma
    # escala», «un grid de veinte puntos»). The turn read it as his to us — `escalate_or_inline=escalate`
    # at 0.73, and neither of the turn's two questions contradicts that, because it WAS an errand; what it
    # was not is OURS — answered «lo mando hacer», and a Brain Worker started rewriting `widgets/youtube`.
    # Forty seconds later: «Olvídate de eso, no va por ti», and the worker carried on. A minute after
    # that: «Lo de modificar el widget de YouTube ha sido un error, y no estaba hablando contigo. Eso lo
    # tienes que parar y deshacer».
    #
    # THE OPERATOR'S RULE, from that same session: «hay que pedir confirmación siempre que pidamos crear
    # un widget o modificar un widget… que sea algo de sistema, porque así nos evitaremos que se empiecen
    # a generar widgets por ahí fuera de cualquier manera».
    #
    # IT GOES HERE, AND THE PLACE IS HALF THE REPAIR. The generator is reached from six different doors —
    # the voice turn, the text channel, the probe, V2-118's create-widget backstop, the promise backstop,
    # and a turn promoted from an injection — and a rule every caller has to remember to apply is not a
    # rule (`zaelar-signup-and-access.md`, same lesson). `_run_session` is the ONLY door that starts a
    # worker, and `kind` is already classified by the time it runs: `kind == "code"` IS «this is going to
    # write or rewrite a card's code», decided by `errand_kind` and not by a verb list of this file's own.
    #
    # Out of scope: the CLUSTER dev worker with code permission (V2-076). That one never touches the
    # operator's catalogue — it brings its own repo and its own authorisation.
    if (kind == "code" and not bool(task.context.get("confirmed"))
            and not _d._dev_worker_params(task.context)):
        from nucleo import errand_kind as _ek_gate
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

    rec = _d._SESSIONS.get(key)
    if rec is None:
        return
    rec.kind = kind
    rec.label = _d._default_label(kind, req)
    _d.sync_state()

    # LA CADENA ENTERA DORMIDA: no is lanza nothing (V2-314). Spawning here is a GUARANTEED death — every tier of
    # the worker chain is in cooldown, and the CLI would burn ~30 s in the pool to die in two. What made this
    # invisible is that `providers.pick()` returns None both when the chain is EMPTY (self-host, no keys: run
    # the local license, the promised fail-open) and when every tier is asleep — so the cooldown we record for
    # the LICENSE tier could never bite, and we spawned straight back into the provider that had just said no.
    # Measured in `find-concert-tickets__es` (2026-08-25 10:53-10:56): license marked out-of-quota until 14:20,
    # then spawned into twice more inside three minutes — 1.8 s, 3.9 s, 1.9 s of life, and a person told three
    # times that a search was starting. `exhausted_until()` is the seam that tells the two Nones apart.
    try:
        from nucleo.workers import providers as _prov
        _sleep_reason = _prov.exhausted_reason()
    except Exception:  # noqa: BLE001
        _sleep_reason = ""
    if _sleep_reason:
        _d.logger.warning(f"dispatch: tarea {key} NO se lanza — cadena de proveedores agotada")
        try:
            from voice.observer import emit
            # `provider_asleep` and not a plain `end`: the round did not fail, it never started. The Master and
            # the harness both need to tell «we tried and it broke» from «we knew it was pointless», or an
            # exhausted quota keeps being scored as a broken product.
            emit("task", "provider_asleep", role="system", text=req[:120],
                 extra={"id": key, "ok": False, "until": _prov.exhausted_until(),
                        "reason": "todos los escalones del worker en cooldown: lanzar es morir"})
        except Exception:
            pass
        rec.status = "done"
        rec.ok = False
        rec.result_summary = _sleep_reason
        await _d._deliver_confirm(rec)          # same one-liner path the confirm-gate uses: speak it and be done
        _d._SESSIONS.pop(key, None)
        _d._task_row("ended_early", rec, state="failed")
        _d.sync_state()
        return

    async with _d._pool():
        if rec.status == "cancelled":         # cancelada mientras esperaba el pool
            _d._SESSIONS.pop(key, None)
            _d._task_row("ended_early", rec, state="cancelled")
            return
        ctx = await _d._compose_context(req, kind)
        # V2-778 F1 — building what the session runs with lives in `nucleo/dispatch_session_steps.py`.
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
                      "dejaste y los datos que ya reuniste están en memoria (consúltalos con mem_cli recall). Haz "
                      "`look` PRIMERO para ver dónde te quedaste y CONTINÚA desde ahí hasta terminar.\n\n") + prompt
        if _brief_bg is not None:
            # V2-301 — the compositor continues pensando: the worker starts YA and the address le arrives inyectada.
            prompt += ("\n\nNOTA (dirección en camino): la DIRECCIÓN detallada de esta investigación — criterios "
                       "duros y blandos, amplitud mínima y baremo — se está componiendo y te llegará como "
                       "instrucción nueva en un momento. NO la esperes parado: haz ya los primeros pasos (PASO 0, "
                       "abrir el sitio, la primera búsqueda) y aplícala en cuanto llegue.")
            _d._attach_brief_followup(_brief_bg, key=key, rec=rec, req=req, kind0=kind)
        # V2-778 F1 — running the session to its delivery lives in `nucleo/dispatch_session_steps.py`.
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


from nucleo import dispatch_session_steps as _dss  # noqa: E402 — V2-778 F1, reads this module back
