"""nucleo/workers/session.py — `WorkerSession`: una sesión de Brain Worker VIVA (V2-038).

Envuelve un `WorkerBackend` y conduce su ciclo de vida: arranca el motor, BOMBEA sus eventos normalizados
(`WorkerEvent`) → actualiza el REGISTRO EN RAM (fuente de verdad, §v2·C) + publica en el bus (`worker.*`) + emite
el chip de actividad + ENTREGA el resultado por voz+UI. Gestiona la **cola de inyección** (↓, §v3·H: pending→
delivered, sin doble entrega) y el **cierre con cortesía** (kill de grupo, §v2·D).

La sesión NO habla con el usuario directamente ni resuelve `ask`/`act` (eso es el plano request/response de
worker_api + el loop supervisor): aquí solo se bombea el stream del backend (spawned/phase/result/error/done) y se
mantiene el registro coherente. Diseño: initiatives/V2-038-brain-workers-interactivos.md.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger

from .base import WorkerBackend, WorkerSpec


@dataclass
class Inject:
    text: str
    ts: float
    state: str = "pending"        # pending | delivered


@dataclass
class SessionRecord:
    """La FILA de una sesión viva en el registro RAM (fuente de verdad). Absorbe lo que antes estaba disperso en
    escalate._tasks / dispatch._INFLIGHT / dispatch._SESSIONS (§v3·G). La proyección serializable la da
    `dispatch.active_sessions()`; los handles (session/task) no viajan al ESTADO ni a /api/tasks."""
    task_id: str
    goal: str
    kind: str = "generic"
    backend: str = ""
    label: str = ""
    phase: str = "en cola"
    status: str = "queued"        # queued | running | done | error | cancelled
    started: float = field(default_factory=time.time)
    native_sid: str = ""
    waiting_on: str = ""          # "" | "user" | "flash"  (lo fija worker_api al aparcar un ask)
    ask: str = ""                 # texto de la pregunta activa (si waiting_on)
    ask_corr: str = ""            # corr_id del ask activo
    result_summary: str = ""
    ok: bool = True
    parent_task_id: str = ""
    depth: int = 0
    trace_id: str = ""            # V2-044: trace de la frase que originó la sesión (encadena todos sus eventos)
    nav_task: str = ""            # kind=web: id de la tarea del navegador (tarjeta) asociada — la fija dispatch
    last_event_at: float = field(default_factory=time.time)
    injects: list = field(default_factory=list)     # [Inject]
    paused: bool = False           # V2-065: SIGSTOP'd (⏻ del operador) — sigue "running" para el registro, pero
                                    # congelado; no confundir con status=cancelled (eso es irreversible)
    # ── observabilidad ESTRUCTURADA del worker (V2-059) ──────────────────────────────────────────────────────
    # El worker abre una sesión de Claude Code con trabajo INTERNO opaco. Para verlo de forma controlada:
    #  · `plan`  = la lista de tareas que el worker DECLARA al empezar (`hbnote plan "a|b|c"`).
    #  · `done`  = cuántos pasos del plan lleva hechos (`hbnote progress --done N`) → progreso = done/len(plan).
    #  · `pct`   = progreso explícito 0-100 si lo reporta (manda sobre done/plan); -1 = derivar/desconocido.
    #  · `note`  = última nota de progreso legible.
    #  · `steps` = anillo de los últimos pasos REALES (derivados del stream: tool + dónde + qué) → debug + UI.
    plan: list = field(default_factory=list)
    done: int = 0
    pct: int = -1
    note: str = ""
    steps: list = field(default_factory=list)
    # AMPLITUD de una investigación (`hbnote considered N --kept M`): cuántos candidatos ha mirado el worker DE
    # VERDAD antes de quedarse con M. Es lo que separa una selección defendible de las tres primeras filas de un
    # buscador, y lo que le permite al cerebro ofrecer «he visto 47, ¿te vale o sigo?» en vez de callar el dato.
    # -1 = no reportado (tarea que no es una investigación, o worker que no lo dijo).
    considered: int = -1
    kept: int = -1
    # Murió porque el PROVEEDOR se quedó sin cuota (no por la tarea) → `{provider, next, text}`. Lo pone el
    # backend al ver el error; `_finish` lo usa para reintentar UNA vez con el escalón de relevo en vez de
    # entregarle al operador un «API Error … Weekly Limit Exhausted» como si fuera su informe.
    provider_down: dict | None = None
    provider_retried: bool = False
    # handles runtime (NO serializar):
    session: "WorkerSession | None" = None
    task: "asyncio.Task | None" = None


class WorkerSession:
    def __init__(self, backend: "WorkerBackend", spec: "WorkerSpec", record: "SessionRecord"):
        self._b = backend
        self._spec = spec
        self._rec = record
        self._stopped = False
        self._model = spec.model or ""     # V2-048: modelo del worker (chip de observabilidad) — lo afina `spawned`
        self._usage: dict = {}             # tokens del `result` (input/output) → chip de tamaño en la fila final
        self._cost = None                  # coste USD del `result` → texto de la fila final (informativo, NO se
                                            # usa para Energy — ver energy_meter.report_worker_usage docstring)
        self._base_url = ""                # endpoint real del escalón que sirvió la sesión (energy_meter, 2026-08-05)
        self._started_at = time.time()     # para medir el PRIMER output del worker (su TTFT) — ver _emit_note
        self._first_output_at = 0.0

    @property
    def alive(self) -> bool:
        return self._b.alive and not self._stopped

    # ── ciclo de vida completo de la sesión ────────────────────────────────────────────────────────────────
    async def run(self, prompt: str) -> None:
        rec = self._rec
        rec.status = "running"
        rec.backend = self._b.name
        rec.phase = "arrancando"
        self._touch()
        self._emit_chip("start", rec.label or _default_label(rec.kind))
        self._bus("worker.spawned", {"id": rec.task_id, "kind": rec.kind, "goal": rec.goal[:120]})
        try:
            await self._b.start(prompt, spec=self._spec)
            async for ev in self._b.events():
                self._touch()
                self._on_event(ev)
                if ev.type == "done":
                    break
        except asyncio.CancelledError:
            logger.info(f"worker[{rec.task_id}]: run CANCELADO")
            rec.status = "cancelled"
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{rec.task_id}]: run falló: {e}")
            rec.status = "error"
            rec.ok = False
            rec.result_summary = rec.result_summary or "No pude completar la tarea."
        finally:
            await self._finish()

    def _on_event(self, ev) -> None:
        rec = self._rec
        d = ev.data or {}
        if ev.type == "spawned":
            rec.native_sid = d.get("native_session_id") or rec.native_sid
            self._model = d.get("model") or self._model
            self._emit_meta_row()                              # V2-048: fila "worker · <backend>" con modelo + capa
        elif ev.type == "phase":
            rec.phase = (d.get("label") or "").strip() or rec.phase
            self._bus("worker.phase", {"id": rec.task_id, "phase": rec.phase})
            if not d.get("quiet"):                             # quiet = acompaña a un `step` rico → no duplicar fila
                self._emit_chip("phase", rec.phase)
        elif ev.type == "step":
            self._emit_step(d)                                 # V2-048: DÓNDE + QUÉ concreto de este paso
            # V2-059: además de la fila del panel, GUARDA el paso en el registro (anillo, cap 12) → /api/tasks +
            # ESTADO ven la actividad REAL del worker (no solo la fase coarse). where/what los compone _tool_step.
            try:
                rec.steps.append({"where": d.get("where", ""), "action": d.get("action", ""),
                                  "target": (d.get("target") or "")[:80], "ts": time.time()})
                if len(rec.steps) > 12:
                    rec.steps = rec.steps[-12:]
            except Exception:
                pass
        elif ev.type == "note":
            self._emit_note(str(d.get("text") or ""))          # narración del worker → observabilidad, no voz
        elif ev.type == "provider_down":
            rec.provider_down = {"provider": d.get("provider") or "", "next": d.get("next") or "",
                                 "text": d.get("text") or ""}
            self._emit_chip("proveedor sin cuota", (d.get("provider") or "") +
                            (f" → relevo a {d['next']}" if d.get("next") else " · sin relevo"), ok=False)
        elif ev.type == "progress":
            self._bus("worker.progress", {"id": rec.task_id, "pct": d.get("pct"), "note": d.get("note")})
        elif ev.type == "result":
            rec.result_summary = str(d.get("summary") or "").strip()
            rec.ok = bool(d.get("ok", True))
            self._usage = d.get("usage") or {}
            self._cost = d.get("cost")
            self._model = d.get("model") or self._model
            self._base_url = d.get("base_url") or self._base_url
            self._bus("worker.result", {"id": rec.task_id, "ok": rec.ok})
        elif ev.type == "say":
            # (por si un backend lo emite explícito) → lo relata el loop; aquí solo al bus.
            self._bus("worker.say", {"id": rec.task_id, "text": (d.get("text") or "")[:400]})
        elif ev.type == "error":
            rec.ok = False
            if d.get("fatal") and not rec.result_summary:
                # el operador debe OÍR que falló (nunca silencio): _finish entrega este summary por voz+UI.
                rec.result_summary = "No pude completar la tarea."
            self._bus("worker.error", {"id": rec.task_id, "message": (d.get("message") or "")[:300]})

    async def _finish(self) -> None:
        rec = self._rec
        # RELEVO DE PROVEEDOR: la tarea no fracasó, se quedó sin gasolina. Se relanza UNA vez —el escalón agotado
        # ya está en cooldown, así que el spawn nuevo coge el siguiente— en vez de entregarle al operador el error
        # crudo del proveedor como si fuera el resultado de lo que pidió.
        if rec.provider_down and not rec.provider_retried and rec.status != "cancelled":
            rec.provider_retried = True
            nxt = rec.provider_down.get("next") or ""
            if nxt:
                try:
                    from nucleo.flash import escalate as _esc
                    _esc.escalate_to_slowbrain(rec.goal, context={
                        "src": "provider_failover", "kind": rec.kind, "trace": rec.trace_id,
                        "depth": int(rec.depth or 0)})
                    rec.result_summary = ""          # sin entrega: la retoma el worker de relevo, sin ruido
                    rec.ok = False
                    logger.warning(f"worker[{rec.task_id}]: proveedor sin cuota → relanzada con «{nxt}»")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"worker[{rec.task_id}]: relevo de proveedor falló: {e}")
                    rec.result_summary = (f"Me he quedado sin cuota en el proveedor de los procesos de fondo y no "
                                          f"he podido relevarlo. Míralo en el panel de estado.")
            else:
                rec.result_summary = ("Me he quedado sin cuota en el proveedor que mueve mis procesos de fondo y "
                                      "no tengo otro configurado, así que esta tarea se queda parada. Lo tienes "
                                      "en el panel de estado.")
        if rec.status not in ("cancelled",):
            rec.status = "done" if rec.ok else "error"
        rec.phase = "terminado" if rec.ok else "sin completar"
        # ENTREGA por voz+UI + [SISTEMA] + memoria, salvo cancelación (el operador ya sabe que la paró).
        if rec.status != "cancelled" and rec.result_summary.strip():
            await _deliver(rec)
        self._bus("worker.done", {"id": rec.task_id, "ok": rec.ok, "status": rec.status})
        # una sesión CANCELADA ya emitió su chip end (ok=False) desde dispatch.cancel_session — re-emitir aquí
        # producía DOS end contradictorios (ok=False y ok=True un segundo después, visto en la demo 2026-07-14).
        if rec.status != "cancelled":
            # V2-048: la fila final lleva los TOKENS (chip de tamaño) + el COSTE + el modelo — cuánto costó la tarea.
            extra = {}
            u = self._usage or {}
            pt, ct = u.get("input_tokens"), u.get("output_tokens")
            if pt is not None:
                extra["prompt_tokens"] = pt
            if ct is not None:
                extra["completion_tokens"] = ct
            if self._model:
                extra["model"] = self._model
            if pt or ct:
                try:
                    from nucleo import energy_meter as _energy
                    _energy.report_worker_usage(
                        base_url=self._base_url, model=self._model,
                        prompt_tokens=pt, completion_tokens=ct,
                    )
                except Exception:
                    pass
            lbl = ""
            try:
                if self._cost:
                    lbl = f"${float(self._cost):.4f}"
            except (TypeError, ValueError):
                pass
            self._emit_chip("end", label=lbl, ok=rec.ok, extra=extra)
        # LEAK FIX (marathon 2026-07-22/23): `run()` sale del bucle en el PRIMER "done" (= primer `result` de
        # stream-json), pero el proceso `claude --print` sigue vivo (modo multi-turno, espera más stdin). dispatch
        # hace `_SESSIONS.pop(key)` justo después de `run()` → se pierde la ÚNICA referencia al backend sin haber
        # matado el proceso: quedaba huérfano para siempre (visto: 14 procesos zombie tras ~2h de batería). Si la
        # sesión no se cerró ya por `stop()` (cancelación explícita), cerramos el backend aquí antes de soltarla.
        if not self._stopped:
            try:
                await self._b.stop()
            except Exception:
                pass

    # ── inyección (↓) ────────────────────────────────────────────────────────────────────────────────────
    async def inject(self, text: str) -> None:
        """Encola una instrucción para el worker (§v3·H). Entrega PRINCIPAL = piggyback (worker_api la sirve al
        próximo contacto del bridge); SECUNDARIA = stdin del backend (motores conversacionales)."""
        text = (text or "").strip()
        if not text:
            return
        self._rec.injects.append(Inject(text=text, ts=time.time()))
        try:
            await self._b.send(text)     # vía secundaria; si el backend encola hasta cerrar turno, no pasa nada
        except Exception:
            pass

    def take_pending_injects(self) -> list[str]:
        """Devuelve las inyecciones pendientes y las marca `delivered` (idempotente, sin doble entrega). La llama
        worker_api al responder a un bridge (piggyback)."""
        out = []
        for inj in self._rec.injects:
            if inj.state == "pending":
                inj.state = "delivered"
                out.append(inj.text)
        return out

    # ── cierre con cortesía ────────────────────────────────────────────────────────────────────────────────
    async def stop(self, *, grace: float = 3.0, reason: str = "operator") -> None:
        if self._stopped:
            return
        self._stopped = True
        self._rec.status = "cancelled"
        try:
            await self._b.stop(grace=grace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: stop backend falló: {e}")
        self._bus("worker.cancelled", {"id": self._rec.task_id, "reason": reason})

    # ── V2-065: pausar ≠ parar (ver workers/base.py) — congela sin marcar `status="cancelled"` ────────────────
    def pause(self) -> bool:
        if self._stopped or not self._b.pause():
            return False
        self._rec.paused = True
        self._bus("worker.paused", {"id": self._rec.task_id})
        return True

    def resume(self) -> bool:
        if self._stopped or not self._b.resume():
            return False
        self._rec.paused = False
        self._bus("worker.resumed", {"id": self._rec.task_id})
        return True

    # ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
    def _touch(self) -> None:
        self._rec.last_event_at = time.time()

    def _bus(self, topic: str, payload: dict) -> None:
        try:
            import bus
            bus.emit_sync(topic, payload)
        except Exception:
            pass

    def _emit_chip(self, phase: str, label: str = "", ok: bool = True, extra: dict | None = None) -> None:
        try:
            from voice.observer import emit
            ex = {"id": self._rec.task_id, "ok": bool(ok)}
            if extra:
                ex.update(extra)
            emit("task", phase, text=label, extra=ex)
        except Exception:
            pass

    # ── V2-048: filas RICAS de observabilidad del worker ─────────────────────────────────────────────────────
    def _emit_meta_row(self) -> None:
        """Al nacer: qué MOTOR + qué MODELO + qué CAPA conduce esta tarea (lo que el operador pidió «qué usa»)."""
        try:
            from voice.observer import emit
            rec = self._rec
            model = self._model or self._spec.model or "(def)"
            emit("worker_start", f"worker · {rec.backend or self._b.name}", text=rec.goal[:120],
                 extra={"id": rec.task_id, "model": model, "layer": rec.kind})
        except Exception:
            pass

    def _emit_note(self, text: str) -> None:
        """Lo que el worker VA DICIENDO mientras trabaja (su razonamiento en voz alta), con el ID de la sesión y el
        sello `worker` para que en el visor se lea «esto viene del brain worker N». Es la fila que llena el hueco
        entre que nace y hace algo: sale en cuanto el modelo emite el bloque de texto, sin esperar a una tool.

        Además mide el **primer output** (`first_output_ms` desde que arrancó la sesión) — el equivalente al TTFT de
        un turno de voz, para poder decir si un worker tardó porque el motor arranca lento o porque el trabajo era
        largo de verdad."""
        t = " ".join((text or "").split())
        if not t:
            return
        try:
            from voice.observer import emit
            rec = self._rec
            ex = {"id": rec.task_id, "src": f"worker:{rec.task_id}", "model": self._model or ""}
            if not self._first_output_at:
                self._first_output_at = time.time()
                ex["first_output_ms"] = round((self._first_output_at - self._started_at) * 1000)
            emit("task", "💬 worker", text=t[:600], extra=ex)
        except Exception:
            pass

    def _emit_step(self, d: dict) -> None:
        """Un PASO: DÓNDE trabaja (badge/categoría por lugar) + QUÉ hace y sobre qué (acción + objetivo)."""
        try:
            from voice.observer import emit
            where = (d.get("where") or "sistema")
            place, kind = _PLACE.get(where, _PLACE["sistema"])
            action = (d.get("action") or "").strip()
            target = (d.get("target") or "").strip()
            text = " ".join(x for x in (action, target) if x)
            emit(kind, place, text=text, extra={"id": self._rec.task_id, "tool": d.get("tool") or ""})
        except Exception:
            pass


# Lugar del worker → (etiqueta del panel, `kind` que fija la CATEGORÍA/filtro y el color). Reutiliza kinds ya
# conocidos (observer._CAT): memoria→memory (púrpura, filtro Memoria), navegador→navegador (filtro Navegador),
# web→search, código/archivo/zaelar/sistema→task (main). Así los pasos del worker se integran en los MISMOS filtros
# que los eventos de primera clase, en vez de un cajón aparte (V2-048).
_PLACE = {
    "web":       ("🌐 web", "search"),
    "memoria":   ("🧠 memoria", "memory"),
    "navegador": ("🧭 navegador", "navegador"),
    "codigo":    ("✏️ código", "task"),
    "archivo":   ("📄 archivo", "task"),
    "zaelar":    ("↩ zaelar", "task"),
    "sistema":   ("· paso", "task"),
}


def _default_label(kind: str) -> str:
    return {"web": "Buscando en la web…", "code": "Trabajando en un widget…",
            "memory": "Actualizando la memoria…", "research": "Investigando…"}.get(kind, "Pensando…")


async def _deliver(rec: "SessionRecord") -> None:
    """Entrega el resultado por los raíles de siempre: proactive (voz+UI) + nota [SISTEMA] + memoria (único
    escritor). Réplica del antiguo dispatch._deliver, ahora por-sesión."""
    summary = rec.result_summary.strip()
    if not summary:
        return
    try:
        from voice import brain_notes
        head = "Tarea completada" if rec.ok else "Tarea sin completar"
        brain_notes.push(f"[SISTEMA] Brain worker · {head}: {summary[:400]}")
    except Exception:
        pass
    # MEMORIA: solo el ÉXITO se recuerda como resultado durable (auditoría 2026-07-14 — el refactor P2 perdió el
    # gate `ok` del one-shot y las tareas FALLIDAS escribían píldoras mid tipo «No pude completar la tarea», ruido
    # que además competía en el recall). El fallo ya llega al operador por voz + nota [SISTEMA]. Procedencia
    # estampada (`meta.source`) para poder auditar/limpiar por origen.
    if rec.ok:
        try:
            from nucleo import memory_agent
            await memory_agent.remember({
                "text": f"[tarea {rec.kind}] {rec.goal} → {summary[:600]}",
                "kind": "result", "level": "mid", "importance": 0.5,
                "meta": {"source": f"worker:{rec.task_id}"},
            })
        except Exception:
            pass
    try:
        from voice import proactive
        await proactive.notify("zaelar", summary, speak=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{rec.task_id}]: entrega proactiva falló: {e}")
