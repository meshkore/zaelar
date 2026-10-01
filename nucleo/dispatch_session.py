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
        env = {"ZAELAR_TASK_REQUEST": req,       # req crudo → registry (elige generador) + backend
               # V2-152: a worker must talk to the engine that SPAWNED it, and until now nothing told it which
               # one that was. All six bridges (`nav_cli`, `mem_cli`, `worker_bridge`, `agent_report`,
               # `widget_cli`, plus `hbsay`) resolve `ZAELAR_BASE` with a hardcoded `localhost:43917` default,
               # and NOBODY set that variable — so an engine on any other port spawned workers that drove a
               # DIFFERENT engine's browser, memory and task cards. Measured on `book-hotel-night-known__es`:
               # the sandbox's own task record stayed empty (`url=""`, `shot_rev=0`) and not one of the owner's
               # browser events reached its timeline, while the worker was really navigating Booking.com — on
               # the operator's live engine. The brain then told the operator, truthfully about ITS record and
               # falsely about the world, that nothing had been opened, and he stopped a task that was working.
               "ZAELAR_BASE": _d._own_base_url()}
        nav_tid = ""
        resume = task.context.get("resume") or {}     # V2-049: {nav_task, native_sid, count} si REANUDA una gestión
        resume_sid = str(resume.get("native_sid") or "") if kind == "web" and trusted else ""
        if kind == "web" and trusted:
            nav_tid = await _d._prepare_web(rec, req, reuse_tid=str(resume.get("nav_task") or ""))
            if nav_tid:
                env["ZAELAR_NAV_TASK"] = nav_tid       # las capturas/acciones de hbweb casan con ESTA tarjeta
        _dev = _d._dev_worker_params(task.context)     # V2-076: escalada de cluster con permiso de código
        _dev_settings_path = ""
        if _dev:
            import tempfile as _tf
            _wd = _tf.mkdtemp(prefix="zaelar-dev-")   # cwd AISLADO para Read/Write/Edit (nunca el proyecto)
            env.update(_dev["env"])
            # GUARD DE CONFINAMIENTO REAL (auditoria 2026-07-26, closes the hallazgo "only convencion of prompt"):
            # hook PreToolUse that deniega Read/Write/Edit/Glob/Grep outside of `_wd` — outside of the own workdir (no
            # inside: so the worker no can touch the file of settings that it confina).
            env["ZAELAR_DEV_WORKER_ROOT"] = _wd
            _dev_settings_path = _d.os.path.join(_tf.gettempdir(), f"zaelar-dev-settings-{key}.json")
            _dev_jail_ok = True
            try:
                _d.dev_worker_guard.write_settings_file(_dev_settings_path)
            except Exception as _e_jail:
                _d.logger.error(   # FAIL-CLOSED, V2-601 T-09 — see test_dev_worker_jail_fails_closed
f"dispatch: could not write the confinement jail for {key} — dev worker starts with NO tools instead of unjailed: {_e_jail!r}")
                _dev_settings_path, _dev_jail_ok = "", False
            spec = _d.WorkerSpec(kind="dev", model=_d._model_for("code"),
                              tools=(_dev["tools"] if _dev_jail_ok else []),
                              deny_tools=(not _dev_jail_ok), trusted=False, task_id=key,
                              token=_d.rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                              env=env, cwd=_wd,
                              extra_args=(["--settings", _dev_settings_path] if _dev_settings_path else []))
        else:
            # OWN CWD (incident 2026-08-18): until today this spec carried no `cwd`, so the backend fell back to
            # the ENGINE ROOT and the headless agent loaded `engine/CLAUDE.md` (76k tokens) plus the parent
            # CLAUDE.md on EVERY request. Measured on the worker that died: 122,833 input tokens BEFORE doing any
            # work, ~62k of headroom, and the provider rejected the call 14 steps later. Measured again head-to-head
            # afterwards: 167,242 tokens in the repo root vs 25,352 in a scratch dir (-84.8%). See
            # `workers/workdir.py` for the three faults one directory per task fixes (context, `informe.json`
            # collision, private CLAUDE.md). `read_dirs` declares the browser's capture directory (it arrives by absolute
            # path outside the cwd, V2-049); measured that the CLI already allows it, so this is defence in depth.
            _may_write = _d.protected_core.writes_are_confined(kind, req)   # V2-655: el ENCARGO, no el kind
            _wd = None
            if not (_may_write and _d.workdir.needs_repo(kind)):
                _wd = _d.workdir.for_task(key)
                env.update(_d.workdir.env_for_task(env))
            _tools, _jail_args = _d.dev_worker_guard.jail_writes(_d._tools_for(kind, trusted, _may_write), _wd, env, key=key)
            spec = _d.WorkerSpec(kind=kind, model=_d._model_for(kind), tools=_tools,   # V2-778 F4-34 — writes-only jail
                              deny_tools=(not trusted), trusted=trusted, task_id=key,
                              token=_d.rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                              env=env, cwd=_wd, resume_sid=resume_sid,
                              read_dirs=(_d.workdir.extra_dirs() if _wd else []), extra_args=_jail_args)
        backend = _d.get_backend(spec)
        session = _d.WorkerSession(backend, spec, rec)
        rec.session = session
        # PRE-VUELO: ¿esto es a research/seleccion? Entonces is dirige with a brief (amplitud + baremo +
        # form of the entregable) in vez of leave that the worker is autoimponga the criterion minimo. Un dev-worker of
        # code no pasa by here: su address es the repo, no a espacio of candidatos.
        brief = None
        _brief_bg: _d.asyncio.Task | None = None
        if not _dev:
            try:
                # V2-301 — the composer is a REASONING call (15-30 s) and it ran IN SERIES before the spawn:
                # measured across the guitar rounds (2026-08-24), the worker sat «in cola» 20-32 s doing
                # nothing while the composer thought, and then spent its OWN first ~20 s on preamble (mesh
                # PASO 0 + memory reads) — two stretches that overlap perfectly. A short head start keeps the
                # instant paths fully-directed (a resumed/round-2 brief returns without any LLM); past it the
                # worker spawns NOW and the brief arrives as an injected turn, through the same channel every
                # refinement already uses. Fail-open unchanged: a composer that dies just means no injection.
                _brief_bg = _d.asyncio.ensure_future(_d._compose_brief(req, ctx, trusted, resume))
                _head = float(_d.os.environ.get("ZAELAR_BRIEF_HEAD_START_S", "2.0") or 2.0)
                if _head <= 0:      # kill-switch: serial, exactly as before
                    brief = await _brief_bg
                    _brief_bg = None
                else:
                    try:
                        brief = await _d.asyncio.wait_for(_d.asyncio.shield(_brief_bg), timeout=_head)
                        _brief_bg = None
                    except _d.asyncio.TimeoutError:
                        brief = None            # still thinking → spawn now, inject when ready
            except _d.research.ComposerUnavailable:
                # El compositor no pudo contestar. El fail-open (start without dirigir) es correcto, but NO can
                # arrastrar consigo the mitad of the budget: that esto sea a research no depende of that the
                # compositor este live. Se promociona the kind IGUAL — cuesta DIRECCIÓN, no TIEMPO. Medido in the
                # banco of the 2026-08-13: the compositor tardo >30 s, the task is quedo in `generic` (600 s) and the
                # worker murio a the 704 s with the browser a medias, the same «agoto su time» that the promocion
                # of abajo exists for close.
                brief = None
                _brief_bg = None    # falló DENTRO del head start: ya está manejado aquí, nada que inyectar luego
                if kind == "generic":
                    rec.kind = "research"
                    rec.label = _d._default_label("research", req)
                    _d.logger.info(f"dispatch: tarea {key} SIN brief (compositor caído) pero con presupuesto de "
                                f"investigación · kind={rec.kind}")
                    _d.sync_state()
            if brief:
                _d.research.save(key, brief)
                _d.research.remember_round(_d._goal_key(req), brief)   # para que una 2ª petición continúe, no reempiece
                if not _d.surfaces.opens_doc(getattr(rec, "surface", "")):   # V2-644: no results sheet to seed
                    await _d._seed_research_criteria(brief)
                rec.phase = "preparando la investigación"
                # EL BRIEF ES LA PRUEBA of that esto es a INVESTIGACIÓN, and with ella is cobra the budget that le
                # corresponde. `loop._kind_budget_default` already reservaba 1200s for `research`… but NADIE asignaba
                # never ese kind: `_classify_kind` only returns web/code/generic, so that toda research that no
                # nombrara Wallapop/Amazon caia in `generic` = 600s. Y ese medio budget CONTRADICE the own
                # brief, that exige reunir ≥40 candidatos and ENTRAR in the ficha of each finalista: 10 minutos no dan
                # for eso, so that the worker moria conminado a «entrega already» with the sheet a medias — es it that le paso
                # al operator the 2026-08-12 two veces («agoto su time»). Only is promociona `generic`: `web`
                # (1200s, and with su reanudacion by `native_sid`) and `code` conservan su path intacta. Y the `spec` of the
                # worker YA esta construido with the kind viejo a purpose — here only cambia it that MIDE the
                # supervisor and it that LEE the operator in the tarjeta («Investigando…», no «Pensando…»).
                if kind == "generic":
                    rec.kind = "research"
                    rec.label = _d._default_label("research", req)
                _d.logger.info(f"dispatch: tarea {key} dirigida por BRIEF (ronda {brief.get('round')}, "
                            f"≥{(brief.get('breadth') or {}).get('min_candidates')} candidatos) · "
                            f"kind={rec.kind}")
                _d.sync_state()
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
        try:
            await session.run(prompt)
        except _d.asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            _d.logger.warning(f"dispatch: sesión {key} falló: {e}")
        finally:
            # V2-049 CONTINUIDAD: ¿operation web that quedo SIN complete? → reanudable (manten the tab live).
            _resumable = (kind == "web" and trusted and rec.status != "cancelled" and not rec.ok)
            _prev_count = int((resume or {}).get("count", 0))
            if nav_tid:
                try:
                    await _d._finalize_web(rec, keep_open=_resumable)
                except Exception:
                    pass
            if _dev:
                # limpieza of the workdir temporary + the settings of the guard (auditoria 2026-07-26, T-07: before no is
                # borraban never — fuga of disco acumulativa with escaladas of code of cluster repetidas).
                try:
                    import shutil as _sh
                    _sh.rmtree(_wd, ignore_errors=True)
                except Exception:
                    pass
                if _dev_settings_path:
                    try:
                        _d.os.remove(_dev_settings_path)
                    except Exception:
                        pass
            if kind == "web" and trusted:
                _d._leave_resume(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                              brief=bool(brief), prev_count=_prev_count)
            try:
                if key.isdigit():
                    escalate.finish(int(key), rec.result_summary if rec.ok else "")
            except Exception:
                pass
            _waiting_user = (rec.waiting_on == "user") or bool(rec.ask)
            # V2-222 — ¿va a CONTINUAR sola? Se calcula here, ANTES of anotar the final, because a session that is
            # resumes sola no ha terminado and anotarla como terminada es it that partia the prompt in two.
            # V2-238 — DOS ESCALADAS PARA UNA MUERTE. `_finish` already relanza the errand when releva of proveedor
            # or compacta the contexto (`escalate_to_slowbrain`), and leaves `ok=False` a purpose for that no haya two
            # entregas. Pero `_resumable` reads exactamente ese `ok=False` and disparaba ADEMÁS the auto-resume of
            # V2-049: two workers sobre the same errand, and —until V2-237— the two reanudando the MISMA session of the
            # CLI, that es como morian a the 400 ms. El testigo already esta pasado: here no is pasa another vez.
            _handoff = str(getattr(rec, "handoff", "") or "")
            _will_resume = bool(_resumable and not _waiting_user
                                and (_prev_count + 1) < _d._RESUME_CAP and not _handoff)
            # …but the ENCARGO continua in the two ways, so that it that mira «¿esto is ha acabado?» mira esto.
            _continues = bool(_will_resume or _handoff)
            # V2-079 → V2-728: the DURABLE trace of the execution that is ending (the live record is popped
            # right here and used to simply disappear). It was a 50-entry JSON blob in `sys_kv`; it is now a
            # row in `tasks`, with no cap, no hand-rolled reset fence and its RESULT hanging off it.
            # Best-effort and off the hot path, as it always was.
            try:
                from nucleo import tasks as _tasks
                _tasks.closed(rec)
            except Exception:  # noqa: BLE001
                pass
            # EXPLICIT flow-close signal (observability, V2-090): without this a flow only ever looks "closed" by
            # the ABSENCE of new events — an inference from silence, never a fact. The task row above already
            # records this worker session's own end; this event is for the FLOW (`corr_id`) that spawned it, so the
            # master's board can mark the column closed for real instead of guessing from recency.
            if getattr(rec, "trace_id", ""):
                try:
                    from voice import trace as _trace2
                    from voice.observer import emit as _emit_flow_end
                    # `trace.scope()` FORCES this event's corr_id to `rec.trace_id`, rather than trusting whatever
                    # trace happens to be ambient in this task's context at finally-time — `emit()` always reads
                    # `trace.current()` for the indexed `corr_id` column, never an `extra` field.
                    with _trace2.scope(rec.trace_id):
                        _emit_flow_end("flow", "end", role="system",
                                        extra={"ok": bool(rec.ok), "status": str(rec.status or "")})
                except Exception:
                    pass
            _d._remember_ended(rec, resuming=_continues)     # V2-199: el final es un HECHO — antes de tirar el registro
            _d._SESSIONS.pop(key, None)
            # V2-227 ambito C — DESPUÉS of the pop, never before: the sheet reads the record live, so that mientras this
            # session siguiera inside `alive` seguiria diciendo that si. Y no al resume: the errand continua.
            if not _continues and _d.surfaces.opens_sheet(getattr(rec, "surface", "")):
                _d._sheet_close(rec)
            elif not _continues and _d.surfaces.opens_doc(getattr(rec, "surface", "")):
                _d._docsheet.doc_close(rec)
            try:
                from nucleo import worker_api
                worker_api.purge_task(key)   # §v3·L: sin asks pendientes de una sesión terminada
            except Exception:
                pass
            try:
                from nucleo.workers import findings
                findings.forget(key)         # V2-236: la memoria de hallazgos se va con su sesión
            except Exception:
                pass
            _d.sync_state()
            # V2-049 AUTO-RESUME: operation web incompleta, SIN question pending, bajo the cap → CONTINÚA sola (the
            # FlashBrain no cesa the task ni waits a empujon of the operator). Con question pending NO: waits the
            # response (that, al arrive como turn, resumes by the same via). Con `ask` the purge of arriba already the
            # quito, by eso leimos _waiting_user ANTES.
            if _will_resume:
                _d._schedule_auto_resume(req)
