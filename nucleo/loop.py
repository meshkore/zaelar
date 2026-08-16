"""nucleo/loop.py — Loop orquestador (~1 Hz), el "hilo del tiempo" del cerebro v2 (V2-005 · T70).

Un bucle async a ~1 Hz que corre en el proceso del server (MISMO loop que la voz, junto al supervisor de
widgets). Es el latido propio de zaelar — reemplaza el **cron nativo de Hermes**, que muere con él. En cada tick:

  - **tareas programadas** — dispara las vencidas del scheduler propio (`nucleo/scheduler.py`, respaldado por
    `memory.journal`) y entrega su prompt por los raíles proactivos (voz + UI).
  - 🔥 **chispas** — pensamiento espontáneo, con doble gate (frecuencia + utilidad, `nucleo/sparks.py`).
  - **consolidación** ("sueño") — dispara `memory.consolidate()` por intervalo, FUERA del hot path
    (`asyncio.to_thread`: el consolidador es sqlite síncrono y no debe bloquear la voz).
  - **confirmaciones caducadas** y **flujos conversacionales abandonados** (2026-08-16) — revisita, en una
    ventana propia más lenta que el pulso, decisiones de cierre que un turno solo pudo tomar UNA vez (ver
    `_supervise_confirms`/`_supervise_stale_flows`). Nunca toca un flujo con un Brain Worker vivo encima.
  - **señales** por el bus: `loop.tick`, `loop.scheduled_fired`, `loop.spark` (observables por el tests/voice/e2e/agent/juez).

Loop-agnóstico: se monta en el lifespan del server como una task (fuerte ref en app.state), como el resto de
subsistemas. NUNCA bloquea la ruta de voz — el trabajo pesado va a un hilo o (V2-007) a un CodeAgent.
Reporta SIEMPRE por `voice/proactive.notify()` (voz + subtítulo + chat, deduplicado) — nunca un toast.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

from . import scheduler as _scheduler
from . import sparks as _sparks


def _emit(topic: str, payload: dict | None = None) -> None:
    """Publica una señal del loop por el Sistema Nervioso (best-effort, loop-agnóstico)."""
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass


async def _default_deliver(title: str, text: str) -> None:
    """Entrega por los raíles proactivos existentes (voz + UI). Best-effort."""
    try:
        from voice import proactive
        await proactive.notify(title or "zaelar", text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"loop deliver failed: {e}")


class OrchestratorLoop:
    """El bucle ~1 Hz. `start()` crea la task; `stop()` la cancela limpiamente."""

    def __init__(self, tick_s: float | None = None, consolidate_every_s: float | None = None,
                 spark_gate: "_sparks.SparkGate | None" = None, deliver=None):
        self.tick_s = float(os.getenv("ZAELAR_LOOP_TICK_SECS", "1.0")) if tick_s is None else tick_s
        self.consolidate_every_s = (
            float(os.getenv("ZAELAR_CONSOLIDATE_SECS", "3600")) if consolidate_every_s is None
            else consolidate_every_s)
        self._gate = spark_gate or _sparks.SparkGate()
        self._deliver = deliver or _default_deliver
        self._task: asyncio.Task | None = None
        self._stop = False
        self._last_consolidate = 0.0
        self._ticks = 0
        # V2-038 · supervisor de Brain Workers (§v2·D §8): relatar preguntas, detectar encallamiento/timeout.
        self._ask_relayed: set[str] = set()       # corr_id de asks ya relatados por voz (una vez)
        self._stuck_informed: set[str] = set()    # tid ya avisados de encallamiento
        self._timeout_informed: set[str] = set()  # tid ya avisados de timeout
        self._budget_nudged: set[str] = set()     # tid ya conminados a ENTREGAR (fase 1 del presupuesto)
        self._stuck_secs = float(os.getenv("WORKER_STUCK_SECS", "180"))
        self._max_secs = float(os.getenv("WORKER_MAX_SECS", "900"))
        # PRESUPUESTO DURO por worker (demo 2026-07-14: la búsqueda de Wallapop vagó 12+ min sin entregar; el
        # aviso pasivo de _max_secs no corta). Dos fases: al agotarse se INYECTA "entrega ya" (el worker cierra
        # con lo que tenga); si tras la gracia sigue vivo, se MATA y se avisa con entrega parcial (la tarjeta
        # conserva lo extraído). Configurable global y por kind (WORKER_BUDGET_SECS / WORKER_BUDGET_WEB_SECS…).
        self._budget_secs = float(os.getenv("WORKER_BUDGET_SECS", "600"))
        self._budget_grace = float(os.getenv("WORKER_BUDGET_GRACE_S", "90"))
        # DEFAULT por-kind más generoso donde la tarea es legítimamente larga: una investigación web COMBINADA
        # (buscar en un marketplace + investigar cada candidato en Google + sintetizar el informe) no cabe en 10 min
        # (batería e2e 2026-07-17: el moto encontró listings reales pero la cita lo mató antes del top-3). El env
        # WORKER_BUDGET_WEB_SECS sigue mandando; la fase-1 (nudge "entrega ya") + la parcial en tarjeta se conservan.
        self._kind_budget_default = {"web": 1200.0, "research": 1200.0}
        # CIERRE de flujos CONVERSACIONALES que se quedaron esperando al operador y nunca volvió (2026-08-16,
        # diagnóstico en vivo: el operador veía "6 activos" en el master de una conversación abandonada hace
        # rato). "La pelota está en el tejado de la gente" solo aplica mientras HAY una gente trabajando en
        # ello — un Brain Worker vivo (`dispatch.has_live_trace`) NUNCA se toca aquí, pase el tiempo que pase;
        # esto es solo para el turno que ya contestó y quedó a la espera de que el operador retome el tema.
        # Comprobación DESACOPLADA del tick de 1 Hz (una query SQL de verdad, no bookkeeping en RAM) — se mira
        # cada `_stale_flow_check_every_s`, no en cada pulso.
        self._stale_flow_secs = float(os.getenv("ZAELAR_STALE_FLOW_SECS", "900"))       # 15 min por defecto
        self._stale_flow_check_every_s = float(os.getenv("ZAELAR_STALE_FLOW_CHECK_SECS", "60"))
        self._last_stale_flow_check = 0.0

    # ── ciclo de vida ────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._task is not None:
            return
        self._stop = False
        self._last_consolidate = time.time()   # no consolidar en el arranque
        # Integridad del embedding (V2-030): avisa (off-hot-path) si el modelo cambió sin re-indexar los vectores.
        try:
            from memory import reembed
            reembed.check()
        except Exception:
            pass
        self._task = asyncio.create_task(self._run(), name="nucleo:orchestrator-loop")
        logger.info(f"Loop orquestador arrancado · tick {self.tick_s:.1f}s · consolida cada "
                    f"{self.consolidate_every_s:.0f}s")

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while not self._stop:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 — un tick que peta NUNCA tumba el loop
                logger.warning(f"loop tick error (ignorado): {e}")
            try:
                await asyncio.sleep(self.tick_s)
            except asyncio.CancelledError:
                break

    # ── un pulso ─────────────────────────────────────────────────────────────────────────────────────────
    async def tick(self) -> None:
        """Un pulso del loop: vencidos del scheduler → chispas → ¿consolidar? → señal `loop.tick`."""
        now = time.time()
        self._ticks += 1
        await self._supervise_workers(now)
        await self._supervise_confirms(now)
        await self._supervise_stale_flows(now)
        await self._fire_due(now)
        await self._maybe_spark(now)
        await self._maybe_consolidate(now)
        _emit("loop.tick", {"ts": now, "n": self._ticks})

    async def _supervise_workers(self, now: float) -> None:
        """V2-038 (§8): PROYECTA el registro RAM al ESTADO (~1 Hz, §v2·C), RELATA la pregunta de un worker que
        espera (una a una, con atribución, §v3·B/M), y avisa de ENCALLAMIENTO/TIMEOUT (nunca mata a ciegas §v3·Q7).
        Best-effort; un fallo aquí nunca tumba el loop."""
        try:
            from nucleo import dispatch, worker_api
        except Exception:
            return
        # (1) proyección coalescada RAM → ESTADO (fuente de verdad = RAM; no per-evento).
        try:
            dispatch.sync_state()
        except Exception:
            pass
        try:
            sessions = dispatch.active_sessions()
        except Exception:
            sessions = []
        live_ids = {s["id"] for s in sessions}
        # limpia marcas de sesiones que ya no existen (para no crecer sin límite)
        self._stuck_informed &= live_ids
        self._timeout_informed &= live_ids
        self._budget_nudged &= live_ids
        # (2) relatar el ask ACTIVO (más antiguo) UNA vez, con atribución + abrir la ventana de atención (§v3·D/N).
        try:
            a = worker_api.active_ask()
        except Exception:
            a = None
        if a and a["corr_id"] not in self._ask_relayed:
            self._ask_relayed.add(a["corr_id"])
            goal = ""
            for s in sessions:
                if s["id"] == a["task_id"]:
                    goal = s.get("goal") or ""
                    break
            try:
                from voice import attention
                attention.note_directed()          # la respuesta inmediata del operador es DIRIGIDA (§v3·D)
            except Exception:
                pass
            await self._deliver("zaelar", self._say(
                "worker_ask_named" if goal else "worker_ask_generic",
                goal=goal[:40], question=a["question"]))
        # purga corr_ids ya resueltos del set de relatados (para no crecer)
        try:
            pend = {p["corr_id"] for p in worker_api.pending_asks()}
            self._ask_relayed &= pend
        except Exception:
            pass
        # (3) encallamiento + timeout (avisa, ofrece parar; NO mata solo) + PRESUPUESTO duro (2 fases).
        for s in sessions:
            tid, age = s["id"], int(s.get("age_s") or 0)
            if s.get("waiting_on") == "user":
                continue                            # no está encallado: espera al operador
            budget = self._budget_for(s.get("kind") or "")
            if budget > 0 and age >= budget + self._budget_grace:
                # FASE 2: agotó presupuesto + gracia sin cerrar → se MATA con entrega parcial (la tarjeta
                # conserva lo extraído vía _finalize_web). Nunca más un worker vagando indefinidamente.
                try:
                    dispatch.cancel_session(tid, reason="budget")
                except Exception:
                    continue
                _emit("worker.budget_kill", {"id": tid, "age_s": age})
                goal = (s.get("goal") or self._lang().generic_task)[:60]
                await self._deliver("zaelar", self._say("worker_budget_killed", goal=goal))
                continue
            if budget > 0 and age >= budget and tid not in self._budget_nudged:
                # FASE 1: conminar a ENTREGAR YA (piggyback/stdin) — el worker cierra con lo que tenga.
                self._budget_nudged.add(tid)
                _emit("worker.budget_nudge", {"id": tid, "age_s": age})
                try:
                    rec = dispatch.get_record(tid)
                    if rec is not None and rec.session is not None:
                        await rec.session.inject(
                            "SE TE ACABA EL TIEMPO: deja de explorar, extrae lo que tengas y ENTREGA AHORA tu "
                            "conclusión final con lo encontrado hasta este momento.")
                except Exception:
                    pass
                continue
            if age >= self._max_secs and tid not in self._timeout_informed:
                self._timeout_informed.add(tid)
                goal = (s.get("goal") or self._lang().generic_task)[:40]
                await self._deliver("zaelar", self._say("worker_timeout_running", goal=goal, minutes=age // 60))
            elif int(s.get("silent_s", age)) >= self._stuck_secs and tid not in self._stuck_informed:
                # ENCALLADO = CALLADO, no «lleva rato». Hasta el 2026-08-02 esto miraba `age` (la edad de la tarea),
                # con la propia nota «aproximado por edad» — así que CUALQUIER worker que pasara de 3 min se
                # declaraba «encallado (sin eventos)» aunque estuviera emitiendo cada 5 s. El Susurro lo creía,
                # re-escalaba, y salían DOS y TRES workers haciendo el mismo trabajo (visto en vivo: 3 workers y
                # ~3× el coste para una sola búsqueda). `last_event_at` ya se mantenía en cada evento; solo faltaba
                # mirarlo. Fallback a `age` si el snapshot es viejo y no trae el campo.
                self._stuck_informed.add(tid)
                _emit("worker.stuck", {"id": tid, "age_s": age, "silent_s": int(s.get("silent_s", age))})

    async def _supervise_confirms(self, now: float) -> None:
        """A pending irreversible-action confirmation the operator never answered must not die in silence
        (2026-08-16, operator request after a diagnosed real incident: two turns asked the same "delete all my
        agenda data" confirmation on the same widget — split by the segmenter — and both sat stuck with no way
        to answer either one, and no signal that anything had gone wrong). `widgets/confirm.py` already closes
        the orphaned/expired confirmation's flow synchronously (so the master stops showing it "EN CURSO"
        forever); this is the other half — telling the operator, over the SAME proactive rails (voice+chat) a
        stuck/timed-out worker already uses just above, so the task doesn't just quietly stay undone."""
        try:
            from widgets import confirm
            expired = confirm.drain_expired_notices()
        except Exception:
            return
        for e in expired:
            q = (e.get("question") or "").strip() or self._lang().generic_task
            await self._deliver("zaelar", self._say("confirm_expired", question=q))

    async def _supervise_stale_flows(self, now: float) -> None:
        """Closes a CONVERSATIONAL flow the operator started and then walked away from (2026-08-16, operator
        request after a diagnosed real incident — the master kept showing several "en curso" flows from a
        session the operator had abandoned minutes earlier). `_maybe_close_flow` (the per-turn path in
        `voice/engine/llm/providers/nucleo.py`) only ever gets ONE chance to close a flow, right when its own
        turn finishes; if that turn correctly deferred (an accumulator chain, a pending confirmation, a live
        worker), nothing EVER revisits the decision once those conditions clear on their own. This is that
        revisit — on a slow, deliberately-throttled timer, never the 1Hz tick itself (a real SQL query, not
        RAM bookkeeping).

        Invariant demanded by the operator, verbatim: "si es una búsqueda activa que mantiene un Brain Worker
        en marcha, eso JAMÁS se tiene que cerrar hasta que se termine — la pelota está en el tejado de la
        gente." `dispatch.has_live_trace` is checked FIRST and is the one condition that can NEVER be
        overridden by staleness, no matter how long it runs."""
        if now - self._last_stale_flow_check < self._stale_flow_check_every_s:
            return
        self._last_stale_flow_check = now
        try:
            from observability import identity, flows as _obs_flows
            from nucleo import dispatch as _disp_stale
            from widgets import confirm as _confirm_stale
            from voice import trace as _trace_stale
            from voice.observer import emit as _emit_stale

            sid = identity.session_info().get("session_id")
            if not sid:
                return
            confirm_trace_ids = {v.get("trace_id") for v in _confirm_stale.pending().values()}
            for f in _obs_flows.flows(limit=200, session_id=sid):
                corr_id = str(f.get("corr_id") or "")
                if not corr_id or f.get("ended_events"):
                    continue                                       # sin trace, o ya cerrado explícitamente
                last_ms = float(f.get("last_ms") or 0)
                age = now - last_ms / 1000.0
                if age < self._stale_flow_secs:
                    continue                                       # todavía dentro de la ventana de gracia
                if _disp_stale.has_live_trace(corr_id):
                    continue                                       # un worker vivo NUNCA se cierra por tiempo
                if corr_id in confirm_trace_ids:
                    continue                                       # esperando el sí/no del operador
                with _trace_stale.scope(corr_id):
                    _emit_stale("flow", "end", role="system",
                                extra={"ok": True, "reason": "stale_no_input", "idle_s": int(age)})
        except Exception as e:  # noqa: BLE001 — un fallo aquí nunca tumba el loop
            logger.warning(f"loop: supervise_stale_flows falló (ignorado): {e}")

    @staticmethod
    def _lang():
        """El catálogo de idioma activo (`voice.engine.core.langs`) — cae a español si el import fallara."""
        try:
            from voice.engine.core import langs
            return langs.current_language()
        except Exception:
            class _Fallback:
                worker_ask_named = "Oye, el proceso «{goal}» pregunta: {question}"
                worker_ask_generic = "Oye, uno de los procesos en marcha pregunta: {question}"
                worker_budget_killed = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                       "encontrado hasta ahora.")
                worker_timeout_running = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
                confirm_expired = ("Dejé de esperar tu confirmación sobre: {question} Dímelo otra vez si quieres "
                                   "que lo haga.")
                generic_task = "la tarea"
            return _Fallback()

    def _say(self, template: str, **kw) -> str:
        """Frase HABLADA por iniciativa propia (preguntas de worker, timeouts…) en el idioma ACTIVO — nunca un
        f-string fijo (V2 fix 2026-07-23: `voice.proactive.notify`/`_deliver` hablan tal cual se les entrega, sin
        pasar por ningún turno del LLM que pudiera re-idiomatizarlo)."""
        return getattr(self._lang(), template).format(**kw)

    def _budget_for(self, kind: str) -> float:
        """Presupuesto de pared por kind (WORKER_BUDGET_<KIND>_SECS manda; luego el global; 0 = sin tope)."""
        try:
            v = os.getenv(f"WORKER_BUDGET_{(kind or '').upper()}_SECS")
            if v:
                return float(v)
        except Exception:
            pass
        return self._kind_budget_default.get(kind or "", self._budget_secs)

    async def _fire_due(self, now: float) -> None:
        # V2-092: con el agente PARADO (⏻) un cron no dispara. Se sale ANTES de `mark_fired`, así que el job sigue
        # VENCIDO y salta en cuanto el operador arranca — parar no pierde el recordatorio, lo aplaza. Un cron que
        # hablara por voz encima de un agente parado sería exactamente el fallo que ⏻ existe para evitar.
        try:
            from nucleo import runstate
            if runstate.stopped():
                return
        except Exception:
            pass
        try:
            jobs = _scheduler.due(now)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scheduler.due failed: {e}")
            return
        for job in jobs:
            d = job.get("detail") or {}
            prompt = (d.get("prompt") or job.get("title") or "").strip()
            name = (d.get("name") or job.get("title") or "zaelar").strip()
            try:
                _scheduler.mark_fired(job, now)   # avanza/cierra ANTES de entregar (idempotente ante fallo de voz)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"scheduler.mark_fired failed: {e}")
            # TRAZABILIDAD (V2-044): cada disparo de cron nace con su trace — la entrega (voz+UI) y lo que derive
            # quedan encadenados al job, igual que una frase del operador. ACOTADO: el loop es una task de larga
            # vida → hay que limpiar el ctxvar al acabar el job (si no, los ticks siguientes heredarían el trace).
            try:
                from voice import trace as _trace
                _trace.begin(f"{name}: {prompt}"[:200], origin="cron")
            except Exception:
                _trace = None
            try:
                _emit("loop.scheduled_fired", {"id": job.get("id"), "name": name, "prompt": prompt})
                if prompt:
                    await self._deliver(name, prompt)
            finally:
                if _trace is not None:
                    _trace.adopt("")

    async def _maybe_spark(self, now: float) -> None:
        if not self._gate.allow(now):
            return
        text = _sparks.propose(now)
        if not text:
            return                                # gate de utilidad: no aporta → se descarta
        self._gate.record(now)
        try:
            from voice import trace as _trace
            _trace.begin(text[:200], origin="proactivo")   # V2-044: la chispa encadena su entrega (acotado abajo)
        except Exception:
            _trace = None
        try:
            _emit("loop.spark", {"text": text})
            await self._deliver("zaelar", text)
        finally:
            if _trace is not None:
                _trace.adopt("")

    async def _maybe_consolidate(self, now: float) -> None:
        if (now - self._last_consolidate) < self.consolidate_every_s:
            return
        self._last_consolidate = now
        try:
            from memory import api as memory
            rep = await asyncio.to_thread(memory.consolidate)   # sqlite síncrono → fuera del hot path
            _emit("loop.consolidated", {k: rep.get(k) for k in ("deduped", "evicted", "promoted")})
            logger.info(f"consolidación (sueño): {rep}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"consolidate failed: {e}")
        # Sueño PROFUNDO «fase REM» (V2-056, memory/rem.py): tras el sueño ligero, si toca por cadencia (diaria,
        # marcador persistente sys_kv → sobrevive reinicios) corre el ciclo profundo — reparar vectores + dedup
        # SEMÁNTICO + síntesis de INSIGHTS (hook LLM de nucleo/memllm, la memoria no importa cerebros) + higiene.
        # Si la higiene alerta (CORAZÓN escribiendo por heurística >50% del día), se emite ALERTA observable.
        try:
            from memory import rem as _rem
            if await asyncio.to_thread(_rem.due):
                from . import memllm as _memllm
                rep = await asyncio.to_thread(_rem.run, _memllm.synthesize_concept_groups,
                                              _memllm.verify_insight_grounded,
                                              _memllm.generate_paraphrases)
                _emit("loop.rem", {k: rep.get(k) for k in
                                   ("repaired", "paraphrased", "sem_deduped", "insights", "ms")})
                hyg = rep.get("hygiene") or {}
                if hyg.get("alert"):
                    try:
                        from voice.observer import emit as _oemit
                        _oemit("alert", "memoria: escritura degradada (sueño REM)", role="system",
                               text=f"el {hyg.get('heuristic_pct')}% de lo escrito en 24h fue por heurística "
                                    f"({hyg.get('heuristic_24h')}/{hyg.get('written_24h')}) — ¿CORAZÓN caído?",
                               extra={"module": "memory", **hyg})
                    except Exception:
                        pass
                logger.info(f"sueño REM: {rep}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"rem failed: {e}")


# ── singleton de proceso (lo monta el lifespan del server) ───────────────────────────────────────────────
_LOOP: OrchestratorLoop | None = None


def get_loop() -> OrchestratorLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = OrchestratorLoop()
    return _LOOP


def start() -> None:
    get_loop().start()


async def stop() -> None:
    global _LOOP
    if _LOOP is not None:
        await _LOOP.stop()
        _LOOP = None


def is_running() -> bool:
    return _LOOP is not None and _LOOP.is_running()
