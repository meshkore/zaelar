# One Brain Worker session, in two steps: building what it runs with (env, the web sheet, the dev jail or the
# writes-only jail, the spec, the brief) and running it to its delivery (V2-778 F1, 2026-10-01).
#
# Moved out of `nucleo/dispatch/session.py::_run_session` (387 lines) with no behaviour change. Every name the
# steps read from `dispatch_session` is read through it (`_ds.<name>`) — and it reads the dispatcher through `_d`
# — so a patch on `nucleo.dispatch` still governs them.
from __future__ import annotations

from nucleo.dispatch import session as _ds


async def build_what_it_runs_with(*, ctx, key, kind, rec, req, task, trusted) -> dict:
    env = {"ZAELAR_TASK_REQUEST": req,       # req crudo → registry (elige generador) + backend
           # V2-152: a worker must talk to the engine that SPAWNED it. The six bridges default `ZAELAR_BASE` to
           # `localhost:43917` and nobody set it, so `book-hotel-night-known__es` drove the operator's LIVE
           # engine while its own record stayed empty — and the brain truthfully said nothing had been opened.
           "ZAELAR_BASE": _ds._d._own_base_url()}
    nav_tid = ""
    resume = task.context.get("resume") or {}     # V2-049: {nav_task, native_sid, count} si REANUDA una gestión
    resume_sid = str(resume.get("native_sid") or "") if kind == "web" and trusted else ""
    if kind == "web" and trusted:
        nav_tid = await _ds._d._prepare_web(rec, req, reuse_tid=str(resume.get("nav_task") or ""))
        if nav_tid:
            env["ZAELAR_NAV_TASK"] = nav_tid       # las capturas/acciones de hbweb casan con ESTA tarjeta
    _dev = _ds._d._dev_worker_params(task.context)     # V2-076: escalada de cluster con permiso de código
    _dev_settings_path = ""
    if _dev:
        import tempfile as _tf
        _wd = _tf.mkdtemp(prefix="zaelar-dev-")   # cwd AISLADO para Read/Write/Edit (nunca el proyecto)
        env.update(_dev["env"])
        # GUARD DE CONFINAMIENTO REAL (auditoria 2026-07-26, closes the hallazgo "only convencion of prompt"):
        # hook PreToolUse that deniega Read/Write/Edit/Glob/Grep outside of `_wd` — outside of the own workdir (no
        # inside: so the worker no can touch the file of settings that it confina).
        env["ZAELAR_DEV_WORKER_ROOT"] = _wd
        _dev_settings_path = _ds._d.os.path.join(_tf.gettempdir(), f"zaelar-dev-settings-{key}.json")
        _dev_jail_ok = True
        try:
            _ds._d.dev_worker_guard.write_settings_file(_dev_settings_path)
        except Exception as _e_jail:
            _ds._d.logger.error(   # FAIL-CLOSED, V2-601 T-09 — see test_dev_worker_jail_fails_closed
                f"dispatch: could not write the confinement jail for {key} — dev worker starts with NO tools "
                f"instead of unjailed: {_e_jail!r}")
            _dev_settings_path, _dev_jail_ok = "", False
        spec = _ds._d.WorkerSpec(kind="dev", model=_ds._d._model_for("code"),
                          tools=(_dev["tools"] if _dev_jail_ok else []),
                          deny_tools=(not _dev_jail_ok), trusted=False, task_id=key,
                          token=_ds._d.rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                          env=env, cwd=_wd,
                          extra_args=(["--settings", _dev_settings_path] if _dev_settings_path else []))
    else:
        # OWN CWD (incident 2026-08-18): without `cwd` the worker loaded `engine/CLAUDE.md` (76k tokens) per call —
        # 122,833 input tokens before any work, rejected 14 steps later; repo root 167,242 vs scratch dir 25,352
        # (-84.8%). See `workers/workdir.py`. `read_dirs` adds the capture dir (V2-049; defence in depth).
        _may_write = _ds._d.protected_core.writes_are_confined(kind, req)   # V2-655: el ENCARGO, no el kind
        _wd = None
        if not (_may_write and _ds._d.workdir.needs_repo(kind)):
            _wd = _ds._d.workdir.for_task(key)
            env.update(_ds._d.workdir.env_for_task(env))
        _tools, _jail_args = _ds._d.dev_worker_guard.jail_writes(_ds._d._tools_for(kind, trusted, _may_write), _wd, env, key=key)
        spec = _ds._d.WorkerSpec(kind=kind, model=_ds._d._model_for(kind), tools=_tools,   # V2-778 F4-34 — writes-only jail
                          deny_tools=(not trusted), trusted=trusted, task_id=key,
                          token=_ds._d.rec_token(rec), parent_task_id=rec.parent_task_id, depth=rec.depth,
                          env=env, cwd=_wd, resume_sid=resume_sid,
                          read_dirs=(_ds._d.workdir.extra_dirs() if _wd else []), extra_args=_jail_args)
    backend = _ds._d.get_backend(spec)
    session = _ds._d.WorkerSession(backend, spec, rec)
    rec.session = session
    # PRE-VUELO: ¿esto es a research/seleccion? Entonces is dirige with a brief (amplitud + baremo +
    # form of the entregable) in vez of leave that the worker is autoimponga the criterion minimo. Un dev-worker of
    # code no pasa by here: su address es the repo, no a espacio of candidatos.
    brief = None
    _brief_bg: _ds._d.asyncio.Task | None = None
    if not _dev and not _ds._d.surfaces.delivers_pictures(getattr(rec, "surface", "")):   # pictures skip the research brief
        try:
            # V2-301 — the composer (15-30 s reasoning call) ran IN SERIES: the worker sat queued 20-32 s
            # (guitar rounds, 2026-08-24). A short head start keeps instant briefs; past it the worker spawns
            # NOW and the brief arrives as an injected turn. Fail-open unchanged.
            _brief_bg = _ds._d.asyncio.ensure_future(_ds._d._compose_brief(req, ctx, trusted, resume))
            _head = float(_ds._d.os.environ.get("ZAELAR_BRIEF_HEAD_START_S", "2.0") or 2.0)
            if _head <= 0:      # kill-switch: serial, exactly as before
                brief = await _brief_bg
                _brief_bg = None
            else:
                try:
                    brief = await _ds._d.asyncio.wait_for(_ds._d.asyncio.shield(_brief_bg), timeout=_head)
                    _brief_bg = None
                except _ds._d.asyncio.TimeoutError:
                    brief = None            # still thinking → spawn now, inject when ready
        except _ds._d.research.ComposerUnavailable:
            # The composer failed: fail-open (start undirected) is right, but the kind is still promoted — it
            # costs DIRECTION, not TIME. Bench 2026-08-13: composer >30 s → `generic` (600 s) → died at 704 s.
            brief = None
            _brief_bg = None    # falló DENTRO del head start: ya está manejado aquí, nada que inyectar luego
            if kind == "generic":
                rec.kind = "research"
                rec.label = _ds._d._default_label("research", req)
                _ds._d.logger.info(f"dispatch: tarea {key} SIN brief (compositor caído) pero con presupuesto de "
                            f"investigación · kind={rec.kind}")
                _ds._d.sync_state()
        if brief:
            _ds._d.research.save(key, brief)
            _ds._d.research.remember_round(_ds._d._goal_key(req), brief)   # para que una 2ª petición continúe, no reempiece
            if not _ds._d.surfaces.not_a_sheet(getattr(rec, "surface", "")):   # V2-644: no results sheet to seed
                await _ds._d._seed_research_criteria(brief, rec)
            rec.phase = "preparando la investigación"
            # THE BRIEF PROVES IT IS RESEARCH, and earns its budget: `loop._kind_budget_default` reserved 1200 s
            # for `research` but `_classify_kind` never assigned it, so research fell in `generic` (600 s) and
            # died «out of time» (twice on 2026-08-12). Only `generic` is promoted; `web`/`code` keep their path.
            # The `spec` keeps the old kind on purpose: only the supervisor's budget and the card label change.
            if kind == "generic":
                rec.kind = "research"
                rec.label = _ds._d._default_label("research", req)
            _ds._d.logger.info(f"dispatch: tarea {key} dirigida por BRIEF (ronda {brief.get('round')}, "
                        f"≥{(brief.get('breadth') or {}).get('min_candidates')} candidatos) · "
                        f"kind={rec.kind}")
            _ds._d.sync_state()
    _out = locals()
    return {k: _out[k] for k in ('_brief_bg', '_dev', '_dev_settings_path', '_wd', 'brief', 'nav_tid', 'resume', 'session', ) if k in _out}


async def run_it_to_its_delivery(*, _dev, _dev_settings_path, _wd, brief, escalate, key, kind, nav_tid, prompt, rec, req, resume, session, trusted) -> dict:
    try:
        await session.run(prompt)
    except _ds._d.asyncio.CancelledError:
        pass
    except Exception as e:  # noqa: BLE001
        _ds._d.logger.warning(f"dispatch: sesión {key} falló: {e}")
    finally:
        # V2-049 CONTINUIDAD: ¿operation web that quedo SIN complete? → reanudable (manten the tab live).
        _resumable = (kind == "web" and trusted and rec.status != "cancelled" and not rec.ok)
        _prev_count = int((resume or {}).get("count", 0))
        if nav_tid:
            try:
                await _ds._d._finalize_web(rec, keep_open=_resumable)
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
                    _ds._d.os.remove(_dev_settings_path)
                except Exception:
                    pass
        if kind == "web" and trusted:
            _ds._d._leave_resume(rec, nav_tid=nav_tid, resume=resume, req=req, key=key,
                          brief=bool(brief), prev_count=_prev_count)
        try:
            if key.isdigit():
                escalate.finish(int(key), rec.result_summary if rec.ok else "")
        except Exception:
            pass
        _waiting_user = (rec.waiting_on == "user") or bool(rec.ask)
        # V2-222 — will it CONTINUE on its own? Computed BEFORE recording the end (a resuming session hasn't ended).
        # V2-238 — TWO ESCALATIONS FOR ONE DEATH: `_finish` already relaunched (`ok=False` on purpose) and
        # `_resumable` fired V2-049's auto-resume too — two workers on one errand, same CLI session, dead at 400 ms.
        _handoff = str(getattr(rec, "handoff", "") or "")
        _will_resume = bool(_resumable and not _waiting_user
                            and (_prev_count + 1) < _ds._d._RESUME_CAP and not _handoff)
        # …but the ENCARGO continua in the two ways, so that it that mira «¿esto is ha acabado?» mira esto.
        _continues = bool(_will_resume or _handoff)
        # V2-079 → V2-728: the DURABLE trace of the ending execution, now a `tasks` row (was a 50-entry
        # `sys_kv` blob) with its RESULT attached. Best-effort, off the hot path.
        try:
            from nucleo.circuit import ledger as _tasks
            _tasks.closed(rec)
        except Exception:  # noqa: BLE001
            pass
        # EXPLICIT flow-close signal (V2-090): a closed flow is a FACT for `corr_id`, not inferred from silence.
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
        _ds._d._remember_ended(rec, resuming=_continues)     # V2-199: el final es un HECHO — antes de tirar el registro
        _ds._d._SESSIONS.pop(key, None)
        # V2-227 ambito C — DESPUÉS of the pop, never before: the sheet reads the record live, so that mientras this
        # session siguiera inside `alive` seguiria diciendo that si. Y no al resume: the errand continua.
        if not _continues and _ds._d.surfaces.opens_sheet(getattr(rec, "surface", "")):
            _ds._d._sheet_close(rec)
        elif not _continues and _ds._d.surfaces.opens_doc(getattr(rec, "surface", "")):
            _ds._d._docsheet.doc_close(rec)
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
        _ds._d.sync_state()
        # V2-049 AUTO-RESUME: incomplete web op, NO pending question, under the cap → it CONTINUES on its own. With
        # a pending question it waits for the answer; `_waiting_user` was read BEFORE the purge above.
        if _will_resume:
            _ds._d._schedule_auto_resume(req)
    _out = locals()
    return {k: _out[k] for k in () if k in _out}
