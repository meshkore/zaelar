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
import os
import re
import time
from dataclasses import dataclass, field

from loguru import logger

from .base import WorkerBackend, WorkerSpec

# CONTEXT BUDGET (incident 2026-08-18). Not the model's real ceiling — deliberately well below it, because the
# provider rejects a call once input PLUS the requested output reservation exceeds its window, and we do not know
# what reservation the CLI asks for. The worker that died reached 138,492 with a ~200k-window model, so the ceiling
# in practice sits somewhere around 140k: warning at 110k leaves room to deliver rather than to be cut off.
# `0` disables the watchdog (the crash path in `_finish` still catches it).
_CTX_BUDGET = int(os.getenv("ZAELAR_WORKER_CTX_BUDGET", "110000"))


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
    # V2-259 — la HOJA de este encargo (`results::<sheet>`), sellada UNA vez por `dispatch._sheet_open`. No es
    # `task_id` a secas y ese fue un defecto real: `escalate._seq` arranca en 0 en cada proceso, así que los ids
    # se REPITEN entre reinicios y el primer encargo de un arranque nuevo caía en la hoja `results--1` de la
    # sesión anterior — que `begin_task(fresh=True)` estrena, o sea BORRA. Justo el «error de borrar búsquedas»
    # que esta iniciativa existe para quitar, reintroducido por la puerta de atrás.
    sheet: str = ""
    # V2-227 — DÓNDE va a ver el operador el resultado, decidido al ENCARGAR y no al entregar. Vocabulario
    # CERRADO (`nucleo/surfaces.py`): lista | item | widget | voz | silenciosa. Se sella UNA vez (`set_once`) y
    # no se re-decide a mitad: cambiar de superficie cuando el operador ya está mirando la primera es peor que
    # haber elegido mal. Vacío = todavía sin sellar (una sesión creada a mano en un test, por ejemplo).
    surface: str = ""
    # V2-227 ámbito C — el HISTORIAL de fases legibles, para la pestaña de PROCESO de la hoja. Anillo corto: es
    # lo que el operador está mirando ahora, no un registro de auditoría (eso ya vive en observabilidad). Va
    # aparte de `steps`, que son los pasos crudos derivados del stream y no se le enseñan a nadie.
    phases: list = field(default_factory=list)     # [{"t": <ts>, "s": "entrando en booking.com"}]
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
    # Died (or is about to) because the CONTEXT no longer fits, not because the provider failed (incident
    # 2026-08-18). A separate family on purpose: relaying to another provider does not fix a blown context — the
    # next one blows up identically — so this puts NOBODY on cooldown; what it does is COMPACT AND CONTINUE with
    # whatever was learned.
    context_full: dict | None = None
    context_retried: bool = False
    # How many AUTOMATIC relaunches led to THIS worker. `context_retried`/`provider_retried` above read like
    # they bound the chain ("relaunched ONCE"), and they do not: they live on the RECORD, and every relay builds
    # a fresh one, so each new worker starts at False and may relay again. Measured on the operator's own engine
    # (2026-08-17, `zaelar.db`): SIX workers for one car search. The first ran 7m47s and died on a context-window
    # error after $2.0897 and 138k tokens; the next four were born 3-8s after the previous one ended and died in
    # ~17s with the SAME error. `depth` was travelling through the relay UNCHANGED, so it could not count it
    # either. Same shape as the sheet id that reset on every process: a per-instance counter read as if it were
    # a global one.
    relay_gen: int = 0
    # V2-238 — UN RELEVO NO ES UNA MUERTE. Cuando una de las dos entregas de `_finish` se completa (relevo de
    # proveedor, compactar-y-continuar), esta sesión no ha fracasado: ha PASADO EL TESTIGO a otra que ya está
    # corriendo. Sin este hecho, `ok=False` la dejaba indistinguible de un worker muerto, y el motor le decía al
    # operador que su tarea «ha MUERTO sin resultado y no se va a reintentar sola» mientras el relevo trabajaba.
    handoff: str = ""             # "" = final de verdad · si no, a dónde pasó el testigo, en legible
    # V2-241 — el TROZO exacto que la puerta paró (`cd /Users/…`, `curl -s https://…`). Se guarda para poder
    # nombrarlo en la corrección —una regla general no le dice cuál de sus comandos sobra— y para que un final
    # sin entrega pueda decir por qué se quedó a medias en vez de callarse.
    perm_denied: str = ""
    ctx_tokens: int = 0             # context size of the last message (for the panel and the watchdog)
    real_model: str = ""            # the model that ACTUALLY ran, when the provider says so (≠ requested alias)
    # handles runtime (NO serializar):
    session: "WorkerSession | None" = None
    task: "asyncio.Task | None" = None


# V2-241 — QUÉ trozo paró la puerta. Una corrección que repite las reglas generales no le dice CUÁL de sus
# comandos sobra; el CLI sí lo nombra, en tres formas distintas y medidas. Devuelve "" si el texto no lo dice —
# nunca se inventa un fragmento, que sería mandarle a reescribir un comando que no escribió.
_DENIED_RE = (
    re.compile(r"following part requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"\bcd in ['\"](.+?)['\"] was blocked", re.I),
    re.compile(r"requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"permissions? to use\s+(\S+)", re.I),
)


def denied_fragment(text: str) -> str:
    """El comando (o la ruta) que la puerta nombró, recortado y en una línea."""
    t = str(text or "")
    for rx in _DENIED_RE:
        m = rx.search(t)
        if m:
            frag = " ".join((m.group(1) or "").split()).strip(" .,:;")
            if frag:
                return frag[:160]
    return ""


#: How many AUTOMATIC relaunches an errand gets before we stop and SAY so. Two, because there are two independent
#: causes (blown context, provider out of quota) and each was written to fire once; what was missing was a bound on
#: the CHAIN. A cap is not a cure — a relay that keeps failing identically is a symptom, not a hiccup — but an
#: unbounded retry on a NON-retryable error spends the operator's money in silence, which is how six workers ran
#: one car search on 2026-08-17.
_RELAY_CAP_DEFAULT = 2


class WorkerSession:
    def __init__(self, backend: "WorkerBackend", spec: "WorkerSpec", record: "SessionRecord"):
        self._b = backend
        self._spec = spec
        self._rec = record
        self._stopped = False
        self._model = spec.model or ""     # V2-048: modelo del worker (chip de observabilidad) — lo afina `spawned`
        self._usage: dict = {}             # tokens del `result` (input/output) → chip de tamaño en la fila final
        self._usage_partial: dict = {}     # tokens ACUMULADOS mensaje a mensaje: lo único que hay si lo matamos
        self._cost = None                  # coste USD del `result` → texto de la fila final (informativo, NO se
                                            # usa para Energy — ver energy_meter.report_worker_usage docstring)
        self._base_url = ""                # endpoint real del escalón que sirvió la sesión (energy_meter, 2026-08-05)
        self._started_at = time.time()     # para medir el PRIMER output del worker (su TTFT) — ver _emit_note
        self._first_output_at = 0.0
        # V2-241 — la corrección del permiso iba UNA vez por sesión (V2-211), y el worker medido chocó TRES.
        # Del segundo choque en adelante nadie le decía nada y moría en silencio, que es exactamente lo que la
        # red pretendía evitar. Ahora se corrige cada choque hasta un tope, y el ÚLTIMO cambia de mensaje.
        self._perm_hits = 0
        self._ctx_warned = False           # the wrap-up turn is injected ONCE (incident 2026-08-18): repeating it
                                            # every message past the budget would spend the little room that is left

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
            _lbl = (d.get("label") or "").strip()
            rec.phase = _lbl or rec.phase
            self._bus("worker.phase", {"id": rec.task_id, "phase": rec.phase})
            # EL DIARIO QUE MIRA EL OPERADOR. Esta línea faltaba, y su ausencia no se parecía a un fallo: la
            # pestaña de PROCESO leía un anillo (`rec.phases`) que solo llenaba `hbnote`, o sea lo que el worker
            # se molestara en narrar. Todo lo que traduce SUS PASOS a una frase —`progress.phrase`, que es la
            # pieza escrita justo para esto— se quedaba en `rec.phase` (una sola línea, la de AHORA) y moría ahí.
            # Medido en la sesión `ed9df756`: catorce pasos de navegador reales y dos entradas en el diario, las
            # dos al final. El operador vio «trabajando» dos minutos y medio.
            try:
                from nucleo import dispatch as _d
                _d.record_phase(rec.task_id, _lbl)   # LA ETIQUETA QUE LLEGA, no `rec.phase`: vacía significa
                #  «la fase la pone otro» (hbnote, más rica), y apuntar la anterior repetiría en el diario un paso
                #  que no ha vuelto a ocurrir.
            except Exception:  # noqa: BLE001
                pass
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
        elif ev.type == "step_result":
            self._emit_step_result(d)                          # 2026-08-10: qué le CONTESTARON a ese paso
            self._maybe_unstick_permission(d)                  # V2-211: ¿ha chocado con NUESTRA propia puerta?
            self._maybe_hand_web(d)                            # V2-236: lo que la BÚSQUEDA trajo, a la conversación
        elif ev.type == "note":
            self._emit_note(str(d.get("text") or ""))          # narración del worker → observabilidad, no voz
        elif ev.type == "context_full":
            # The context no longer fits. NOT a provider fault (see `providers.is_context_overflow`) — nobody goes on
            # cooldown; `_finish` compacts what was learned and hands it to a fresh session.
            rec.context_full = {"text": d.get("text") or "", "tokens": int(d.get("tokens") or 0)}
            self._emit_chip("contexto agotado", f"{rec.context_full['tokens']:,} tokens".replace(",", "."), ok=False)
        elif ev.type == "provider_down":
            rec.provider_down = {"provider": d.get("provider") or "", "next": d.get("next") or "",
                                 "text": d.get("text") or ""}
            self._emit_chip("proveedor sin cuota", (d.get("provider") or "") +
                            (f" → relevo a {d['next']}" if d.get("next") else " · sin relevo"), ok=False)
        elif ev.type == "progress":
            self._bus("worker.progress", {"id": rec.task_id, "pct": d.get("pct"), "note": d.get("note")})
        elif ev.type == "usage":
            # CONSUMO PARCIAL, mensaje a mensaje (2026-08-13). Se acumula aparte del `usage` del `result` porque
            # sirve a un caso que el `result` no puede cubrir: el worker MATADO por presupuesto nunca lo emite. No
            # se suma al total final si el `result` llega —ese ya viene sumado por el CLI— sino que se conserva como
            # el MÍNIMO declarado. Ver `_finish`.
            u = d.get("usage") or {}
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
                try:
                    self._usage_partial[k] = self._usage_partial.get(k, 0) + int(u.get(k) or 0)
                except (TypeError, ValueError):
                    pass
            self._model = d.get("model") or self._model
            self._base_url = d.get("base_url") or self._base_url
            # THE NUMBER THAT PREDICTS DEATH was already flowing past here and we only used it to bill the
            # post-mortem (incident 2026-08-18). Two different things, and telling them apart is the whole point:
            # `_usage_partial` above ACCUMULATES spend; `ctx_tokens` is the size of the LAST request. When it
            # crosses the budget the worker gets ONE turn asking it to deliver what it has — the session is still
            # alive, so we can just talk to it, which beats letting it die and reconstructing the work afterwards.
            rec.real_model = d.get("real_model") or rec.real_model
            ctx = int(d.get("ctx_tokens") or 0)
            if ctx:
                rec.ctx_tokens = ctx
                self._maybe_warn_context(ctx)
        elif ev.type == "result":
            rec.result_summary = str(d.get("summary") or "").strip()
            rec.ok = bool(d.get("ok", True))
            self._usage = d.get("usage") or {}
            self._cost = d.get("cost")
            self._model = d.get("model") or self._model
            rec.real_model = d.get("real_model") or rec.real_model
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

    _RELAY_CAP = _RELAY_CAP_DEFAULT

    async def _finish(self) -> None:
        rec = self._rec
        # COMPACT AND CONTINUE (incident 2026-08-18). The context blew up, which is neither a task failure nor a
        # provider failure, so neither of the two existing paths fits: there is nothing to relay to (the next tier
        # would blow up identically) and nothing to report (the operator asked for a guitar, not for an API error).
        # It is relaunched ONCE carrying what was learned, so the fresh worker does not start from zero.
        if (rec.context_full and not rec.context_retried and not rec.provider_down
                and rec.status != "cancelled" and rec.relay_gen < self._RELAY_CAP):
            rec.context_retried = True
            try:
                from nucleo.flash import escalate as _esc
                _esc.escalate_to_slowbrain(context_handoff(rec), context={
                    "src": "context_handoff", "kind": rec.kind, "trace": rec.trace_id,
                    "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
                rec.result_summary = ""       # sin entrega: la retoma el worker nuevo, sin ruido
                rec.ok = False
                rec.handoff = "contexto agotado → sesión nueva con lo aprendido"
                logger.warning(f"worker[{rec.task_id}]: contexto agotado "
                               f"({rec.context_full.get('tokens')} tok) → retomada con lo aprendido")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{rec.task_id}]: no pude retomar tras agotar el contexto: {e}")
                rec.ok = False                    # V2-238: ver la nota de abajo — esto NO se entrega como logro
                rec.result_summary = ("Me he quedado sin espacio de contexto en esa tarea y no he podido retomarla. "
                                      "Si me la pides otra vez, la parto en trozos más pequeños.")
        # RELEVO DE PROVEEDOR: la tarea no fracasó, se quedó sin gasolina. Se relanza UNA vez —el escalón agotado
        # ya está en cooldown, así que el spawn nuevo coge el siguiente— en vez de entregarle al operador el error
        # crudo del proveedor como si fuera el resultado de lo que pidió.
        if (rec.provider_down and not rec.provider_retried and rec.status != "cancelled"
                and rec.relay_gen < self._RELAY_CAP):
            rec.provider_retried = True
            nxt = rec.provider_down.get("next") or ""
            if nxt:
                try:
                    from nucleo.flash import escalate as _esc
                    _esc.escalate_to_slowbrain(rec.goal, context={
                        "src": "provider_failover", "kind": rec.kind, "trace": rec.trace_id,
                        "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
                    rec.result_summary = ""          # sin entrega: la retoma el worker de relevo, sin ruido
                    rec.ok = False
                    rec.handoff = f"proveedor sin cuota → relevo a «{nxt}»"
                    logger.warning(f"worker[{rec.task_id}]: proveedor sin cuota → relanzada con «{nxt}»")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"worker[{rec.task_id}]: relevo de proveedor falló: {e}")
                    rec.ok = False
                    rec.result_summary = (f"Me he quedado sin cuota en el proveedor de los procesos de fondo y no "
                                          f"he podido relevarlo. Míralo en el panel de estado.")
            else:
                # V2-238 — LOS TRES CAMINOS QUE NO SON UN RELEVO CIERRAN `ok`. Las tres ramas de arriba escriben un
                # `result_summary` que ANUNCIA un fallo, y ninguna tocaba `ok`, que nace en True. Si el backend no
                # lo había cerrado ya, esa frase salía entregada como «Tarea completada: me he quedado sin cuota…»
                # — la avería exacta que persigue V2-092/V2-236: un final que dice lo contrario de lo que pasó.
                rec.ok = False
                rec.result_summary = ("Me he quedado sin cuota en el proveedor que mueve mis procesos de fondo y "
                                      "no tengo otro configurado, así que esta tarea se queda parada. Lo tienes "
                                      "en el panel de estado.")
        # LA CADENA SE PARÓ: hay que decirlo, y decir la VERDAD. Sin esto, un final capado seguía llevando el error
        # crudo del proveedor en `result_summary`, y `operator_safe_summary` lo traduce a «me he quedado sin espacio
        # de contexto… LA RETOMO con lo que llevaba» — una promesa de reintento que ya no va a ocurrir. Una frase
        # tranquilizadora que miente es peor que el error crudo: el operador se queda esperando algo que nadie está
        # haciendo, que es la avería de V2-185 en otra puerta.
        if (rec.relay_gen >= self._RELAY_CAP and not rec.handoff and rec.status != "cancelled"
                and (rec.context_full or rec.provider_down)):
            rec.ok = False
            _veces = int(rec.relay_gen or 0) + 1
            if rec.context_full:
                rec.result_summary = (
                    f"He intentado esa tarea {_veces} veces y las {_veces} me he quedado sin espacio de contexto, "
                    f"así que paro en vez de seguir gastando. Pídemela por partes y la saco.")
            else:
                rec.result_summary = (
                    f"He intentado esa tarea {_veces} veces y el proveedor que mueve mis procesos de fondo ha "
                    f"fallado las {_veces}, así que paro. Lo tienes en el panel de estado.")

        # V2-241 — UN FINAL MUDO TRAS CHOCAR CON LA PUERTA. Los tres casos medidos murieron sin decir nada, y la
        # causa solo aparecía cruzando el log del motor. Si la sesión se acaba sin entrega y sin relevo pero
        # chocó con nuestra propia puerta, ESO es lo que le pasó, y es lo que el operador tiene que oír: no es un
        # fallo de la tarea, es que la vía que eligió está cerrada aquí.
        if (not rec.ok and not rec.handoff and rec.perm_denied and rec.status != "cancelled"
                and not rec.result_summary.strip()):
            rec.result_summary = (
                f"Me he quedado a medias: el comando `{rec.perm_denied}` no está permitido en el cajón donde "
                f"corren mis procesos de fondo, y no hay forma de aprobarlo desde aquí. Si me dices por dónde "
                f"seguir, lo retomo por otra vía.")
        if rec.status not in ("cancelled",):
            rec.status = "done" if rec.ok else ("relevada" if rec.handoff else "error")
        if rec.ok:
            rec.phase = "terminado"
        else:
            rec.phase = "relevada" if rec.handoff else "sin completar"
        # ENTREGA por voz+UI + [SISTEMA] + memoria, salvo cancelación (el operador ya sabe que la paró).
        if rec.status != "cancelled" and rec.result_summary.strip():
            await _deliver(rec)
        self._bus("worker.done", {"id": rec.task_id, "ok": rec.ok, "status": rec.status})
        # LOS TOKENS SE COBRAN SIEMPRE, tambien si la sesión se CANCELÓ (2026-08-13). Esto vivía dentro del
        # `if rec.status != "cancelled"` de abajo, que existe por una razón de INTERFAZ (no pintar dos filas `end`
        # contradictorias) y se llevaba por delante una de FACTURACIÓN que no tiene nada que ver: un worker matado
        # por presupuesto había consumido tokens REALES y se metraba a CERO. Medido en el banco: 704 s, 256 pasos,
        # ~$0,20 de tokens de xAI → €0 facturados. Dos preocupaciones distintas en un solo `if`; se separan.
        u = self._usage or self._usage_partial or {}
        pt, ct = u.get("input_tokens"), u.get("output_tokens")
        # El input CACHEADO es una LÍNEA FACTURABLE APARTE y no va dentro de `input_tokens` (el usage con forma
        # Anthropic lleva los tres contadores separados). En una sesión agéntica larga el mismo prefijo de prompt
        # se relee en cada turno, así que los tokens de caché acaban siendo VARIAS VECES los de input fresco:
        # medido contra el coste que reporta el propio CLI de Grok, ignorarlos nos dejaba el 29% de la factura
        # fuera (211k cacheados frente a 74k de input). Se pasa al metro, que lo tariffa a su precio propio.
        cached = u.get("cache_read_input_tokens")
        if pt or ct or cached:
            from nucleo import energy_meter as _energy
            # THE MODEL THAT ACTUALLY RAN, not the alias we asked for (incident 2026-08-18): the run recorded as
            # `claude-opus-4-8[1m]` was performed by `glm-4.7`, and the tariff table looks the model up BY NAME —
            # so the bill was computed at Opus prices for a GLM run. The alias only decides pricing when the
            # provider never said what it served.
            _energy.report_worker_usage(
                base_url=self._base_url, model=(rec.real_model or self._model),
                prompt_tokens=pt, completion_tokens=ct, cached_tokens=cached,
            )
        # una sesión CANCELADA ya emitió su chip end (ok=False) desde dispatch.cancel_session — re-emitir aquí
        # producía DOS end contradictorios (ok=False y ok=True un segundo después, visto en la demo 2026-07-14).
        if rec.status != "cancelled":
            # V2-048: la fila final lleva los TOKENS (chip de tamaño) + el COSTE + el modelo — cuánto costó la tarea.
            extra = {}
            if pt is not None:
                extra["prompt_tokens"] = pt
            if ct is not None:
                extra["completion_tokens"] = ct
            if self._model or rec.real_model:
                # The panel showed the alias, so it LIED about which model ran. The real one wins; the alias is
                # kept beside it, because "what we asked for" is what a routing/config bug is diagnosed from.
                extra["model"] = rec.real_model or self._model
                if rec.real_model and self._model and rec.real_model != self._model:
                    extra["model_requested"] = self._model
            if rec.ctx_tokens:
                extra["ctx_tokens"] = rec.ctx_tokens
            lbl = ""
            try:
                if self._cost:
                    lbl = f"${float(self._cost):.4f}"
            except (TypeError, ValueError):
                pass
            # UN FINAL DICE POR QUÉ (V2-237, 2026-08-21). La fila del final salía con el coste y nada más, así que
            # un worker MUERTO dejaba `text:""` y el motivo había que ir a buscarlo cruzando el log del motor por
            # `span=worker:N`. Medido por el arnés en `best-plumber-same-day`: los únicos eventos de error de la
            # ronda eran del worker que NO murió, y los cuatro que sí murieron no dijeron nada. Un final sin causa
            # se lee igual que un final normal.
            #
            # Va el texto CRUDO a propósito: esta fila es del registro, no de la boca del operador. De que un error
            # de proveedor no se le lea en voz alta ya se encarga `operator_safe_summary` en la entrega, y su
            # propio docstring dice que el texto completo se queda en el log — que es justo esto.
            extra["status"] = str(rec.status or "")
            if rec.handoff:
                # V2-238 — y si PASÓ EL TESTIGO, la fila lo dice con ese nombre. Un relevo entregaba aquí el mismo
                # final vacío que un muerto (`result_summary` se vacía a propósito para que el operador no vea dos
                # entregas), así que en el registro los dos se leían igual.
                extra["handoff"] = rec.handoff
                lbl = f"{lbl} · relevada: {rec.handoff}".strip(" ·")
            elif not rec.ok:
                why = " ".join(str(rec.result_summary or "").split())[:200]
                lbl = f"{lbl} · {why}".strip(" ·") if why else (lbl or str(rec.status or "sin completar"))
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

    def _maybe_warn_context(self, ctx: int) -> None:
        """Nearing the context ceiling → ask the worker, ONCE, to deliver what it already has (incident 2026-08-18).

        Why talk to it instead of killing it: the session is ALIVE and its own reasoning is the cheapest possible
        summary of its progress — far better than anything we could reconstruct from `steps`/`plan` afterwards. It is
        the same stdin injection channel `send_to_worker` already uses, so no new machinery. Best-effort throughout:
        failing to warn must never be what breaks a task that is still working."""
        rec = self._rec
        if self._ctx_warned or _CTX_BUDGET <= 0 or ctx < _CTX_BUDGET:
            return
        self._ctx_warned = True
        logger.warning(f"worker[{rec.task_id}]: contexto en {ctx} tokens (tope {_CTX_BUDGET}) → pido entrega")
        self._emit_chip("contexto casi lleno", f"{ctx} tokens — pidiendo entrega", ok=False)
        try:
            from voice.observer import emit
            emit("task", "⚠️ contexto casi lleno", text=f"{ctx} tokens — le pido que entregue lo que tiene",
                 extra={"id": rec.task_id, "src": f"worker:{rec.task_id}", "ctx_tokens": ctx})
        except Exception:
            pass
        asyncio.create_task(self._ask_for_delivery())

    # V2-211 — LA PUERTA ES NUESTRA, y el worker se muere en ella sin decirlo. Tres casos medidos el mismo día,
    # tres comandos distintos, la misma forma: `cd … was blocked`, `requires approval: curl -s …`, `requires
    # approval: cd /Users/…`. En headless nadie aprueba, así que la petición de aprobación es un callejón sin
    # salida; el worker lo lee como un no y para, y el turno sigue contando que avanza.
    #
    # `dispatch_prompts` lo ataca por delante (las reglas del cajón, igual que el intérprete en 2026-08-02); esto
    # es la RED: si aun así choca, se le dice EN EL MOMENTO qué ha pasado y cómo se reescribe. La misma forma que
    # la entrega anticipada de arriba —un turno inyectado, UNA vez— porque la sesión sigue viva y su propio
    # razonamiento es el camino más corto de vuelta.
    _DENIED_NEEDLES = ("requires approval", "was blocked", "permission to use", "requested permissions",
                       "may only change directories")

    def _maybe_hand_web(self, d: dict) -> None:
        """Lo que una BÚSQUEDA WEB devuelve va a la conversación en el momento, no cuando el worker entregue.

        Aquí y no en cada backend: `where` ya viene normalizado por el sustrato (`_PLACE`), así que esto cubre a
        Claude Code, a Codex y a Grok con un solo sitio — y a las tools NATIVAS de cada CLI, que es donde el arnés
        midió el dato bueno perdiéndose. Un `is_error` no se empuja: un fallo de la tool no es un hallazgo, y ya
        tiene su propio camino (`_maybe_unstick_permission`, el chip del panel).
        """
        try:
            if str(d.get("where") or "") != "web" or d.get("is_error"):
                return
            from nucleo.workers import findings
            findings.hand_web_finding(self._rec.task_id, str(d.get("text") or ""), self._rec.goal)
        except Exception:  # noqa: BLE001
            pass

    _PERM_MAX = 3          # los que midió el arnés en un solo worker antes de morir callado

    def _maybe_unstick_permission(self, d: dict) -> None:
        raw = " ".join(str(d.get(k) or "") for k in ("text", "result", "output", "target"))
        txt = raw.lower()
        if not txt or not any(n in txt for n in self._DENIED_NEEDLES):
            return
        if self._perm_hits >= self._PERM_MAX:
            return
        self._perm_hits += 1
        last = self._perm_hits >= self._PERM_MAX
        self._rec.perm_denied = denied_fragment(raw) or self._rec.perm_denied
        self._emit_chip("comando no permitido",
                        (f"{self._perm_hits}º choque · " if self._perm_hits > 1 else "")
                        + ("le pido que entregue lo que tenga" if last else "le digo cómo reescribirlo"),
                        ok=False)
        try:
            from voice.observer import emit
            emit("task", "⚠️ el worker chocó con una puerta de permiso",
                 text=raw[:200], extra={"id": self._rec.task_id, "src": f"worker:{self._rec.task_id}",
                                        "hit": self._perm_hits, "denied": self._rec.perm_denied})
        except Exception:
            pass
        asyncio.create_task(self._explain_permissions(last=last))

    async def _explain_permissions(self, *, last: bool = False) -> None:
        """Injects the corrective turn. Separate coroutine because `_on_event` is synchronous."""
        try:
            from nucleo.workers.claude_session import bridge_python
            py = bridge_python()
        except Exception:
            py = "python"
        # V2-241 — el ÚLTIMO aviso no repite las reglas: si tres reescrituras no han bastado, seguir corrigiendo
        # es pedirle lo mismo por cuarta vez. Lo que hace falta es que ENTREGUE lo que tiene antes de morir, que
        # es la diferencia entre una tarea incompleta y una tarea muda.
        if last:
            try:
                await self._b.send(
                    "AVISO DEL SISTEMA: van tres comandos parados por el cajón donde corres, y aquí nadie los va a "
                    "aprobar nunca. DEJA esa vía: no la reintentes. Entrega AHORA lo que ya tengas por el camino "
                    "de entrega habitual, y di explícitamente qué te ha faltado y por qué —«el comando X no está "
                    "permitido aquí»— para que se pueda retomar. Terminar en silencio es el único desenlace que "
                    "no vale.")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{self._rec.task_id}]: no pude pedir la entrega tras el permiso: {e}")
            return
        fragmento = (self._rec.perm_denied or "").strip()
        detalle = (f"El trozo que ha parado es: `{fragmento}`. " if fragmento else "")
        try:
            await self._b.send(
                f"AVISO DEL SISTEMA: {detalle}Ese comando no lo ha rechazado ninguna persona — lo ha parado el "
                "cajón donde "
                "corres, y aquí NADIE puede aprobarlo, así que reintentarlo igual no va a funcionar nunca. "
                f"Reescríbelo: UN solo comando por llamada (sin `&&`, `;`, `|` ni `$(…)`), sin SALIR de tu "
                f"directorio (no solo `cd`: tampoco `ls`/`find`/`cat` de carpetas del repo — los puentes "
                f"funcionan desde donde estás), y solo los puentes `{py} -m nucleo.…` — "
                "para abrir una página `nav_cli`, para buscar `worker_bridge`, nada de `curl` ni scripts propios. "
                "Si lo que necesitabas no se puede hacer así, DILO en tu entrega en vez de terminar en silencio."
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: no pude explicar el permiso: {e}")

    async def _ask_for_delivery(self) -> None:
        """Injects the wrap-up turn. Separate coroutine because `_on_event` is synchronous."""
        try:
            await self._b.send(
                "AVISO DEL SISTEMA: te estás quedando sin contexto y la próxima llamada puede fallar. "
                "PARA de investigar AHORA y entrega lo que YA tengas, aunque esté incompleto: escribe el informe "
                "con los hallazgos actuales y preséntalo por el camino de entrega habitual. Di explícitamente qué "
                "te ha faltado por comprobar, para que se pueda retomar."
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: no pude pedir la entrega anticipada: {e}")

    def _emit_step(self, d: dict) -> None:
        """Un PASO: DÓNDE trabaja (badge/categoría por lugar) + QUÉ hace y sobre qué (acción + objetivo)."""
        try:
            from voice.observer import emit
            where = (d.get("where") or "sistema")
            place, kind = _PLACE.get(where, _PLACE["sistema"])
            action = (d.get("action") or "").strip()
            target = (d.get("target") or "").strip()
            text = " ".join(x for x in (action, target) if x)
            emit(kind, place, text=text,
                 extra={"id": self._rec.task_id, "tool": d.get("tool") or "",
                        "span": f"worker:{self._rec.task_id}"})
        except Exception:
            pass

    def _emit_step_result(self, d: dict) -> None:
        """La EVIDENCIA del paso: qué le contestó la herramienta (2026-08-10).

        Los `tool_result` del stream se descartaban como «ruido interno», y con ellos se iba lo único que permite
        auditar un worker de verdad: se veía que buscó en tal sitio y abrió tal URL, **nunca lo que encontró**. Un
        worker que trae basura y otro que trae el dato exacto dejaban EL MISMO rastro. Va recortado (no resumido —
        un resumen es una interpretación) y en la misma familia que su paso, para que se lea seguido: pido → me
        contestan."""
        try:
            from voice.observer import emit
            body = str(d.get("text") or "").strip()
            if not body:
                return
            where = (d.get("where") or "sistema")
            place, kind = _PLACE.get(where, _PLACE["sistema"])
            bad = bool(d.get("is_error"))
            emit(kind, place + (" ⚠️ error" if bad else " ↩"), text=body,
                 extra={"id": self._rec.task_id, "tool": d.get("tool") or "", "evidence": True,
                        "is_error": bad, "span": f"worker:{self._rec.task_id}"})
            # CEGUERA: un error de cuota de las TOOLS del proveedor no hace fallar la llamada al modelo, así que no
            # dispara el relevo y el worker sigue razonando SIN poder buscar. Sin esto no había ni alerta ni rastro:
            # el worker parecía sano y entregaba conclusiones sin material. Ver `providers.note_tool_blindness`.
            if bad:
                try:
                    from nucleo.workers import providers as _prov
                    _prov.note_tool_blindness(body, tool=str(d.get("tool") or ""),
                                              provider=str(d.get("provider") or ""))
                except Exception:
                    pass
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


def operator_safe_summary(summary: str) -> str:
    """LAST GATE before a worker's summary is spoken and written to the chat wall (incident 2026-08-18).

    A raw provider error is NEVER a report. The operator asked for a guitar and got
    «API Error: The model has reached its context window limit.» — read aloud, in English, as if it were the answer.
    The 2026-08-10 quota incident closed this for its own error class by classifying it upstream; this closes it for
    the class as a WHOLE, so the next unforeseen provider message does not reach the operator either.

    It lives here, at the delivery point, ON PURPOSE: the specific paths (`provider_down`, `context_full`) each
    already replace the text with something readable, but they only cover the failures we anticipated. This one
    covers the rest, and it is a translation, never a silence — the operator always learns the task did not finish;
    what disappears is the internal wording. The full text stays in the log and in the record."""
    t = (summary or "").strip()
    if not t:
        return ""
    try:
        from nucleo.workers import providers as _prov
        if _prov.is_context_overflow(t):
            return ("Me he quedado sin espacio de contexto a mitad de esa tarea. La retomo con lo que llevaba; "
                    "si vuelve a pasar, pídemela por partes.")
        if _prov.classify_failure(t):
            return ("El proveedor que mueve mis procesos de fondo me ha dado un problema con esa tarea. "
                    "Lo tienes en el panel de estado.")
    except Exception:
        pass
    # A bare «API Error…» with no classification is still not a report: it is the CLI talking to us, not to them.
    if t.lower().startswith("api error"):
        return "Esa tarea no ha podido completarse por un fallo del proveedor. Lo tienes en el panel de estado."
    return t


def context_handoff(rec: "SessionRecord") -> str:
    """The brief a fresh worker inherits when the previous one ran out of context (incident 2026-08-18).

    Built ONLY from what we already hold in the record — plan, steps taken, last narrated note, breadth reported.
    No LLM call: compacting must not depend on a model being reachable at the exact moment one just failed, and this
    runs on the failure path.

    What it deliberately does NOT carry is the dead worker's `result_summary`: on this path that field holds the raw
    provider error, and pasting it in would tell the new worker its predecessor's error message was a finding."""
    parts = [f"RETOMA esta tarea, que se quedó a medias porque el worker anterior agotó su contexto: {rec.goal}"]
    if rec.plan:
        done = max(0, min(int(rec.done or 0), len(rec.plan)))
        parts.append("Su plan era: " + " · ".join(str(p) for p in rec.plan[:8])
                     + f" (llevaba {done} de {len(rec.plan)} pasos).")
    if rec.note:
        parts.append(f"Lo último que dijo: {str(rec.note)[:300]}")
    if rec.steps:
        seen: list[str] = []
        for s in rec.steps[-8:]:
            bit = " ".join(x for x in (str(s.get("action") or ""), str(s.get("target") or "")) if x).strip()
            if bit and bit not in seen:
                seen.append(bit)
        if seen:
            parts.append("Ya había mirado: " + " · ".join(seen)[:600] + ".")
    if int(rec.considered or -1) > 0:
        parts.append(f"Había revisado {rec.considered} candidatos y se quedaba con {max(0, int(rec.kept or 0))}.")
    parts.append("NO repitas lo ya mirado: sigue desde ahí y ENTREGA en cuanto tengas algo presentable, "
                 "aunque sea parcial. Ve al grano — el contexto es limitado.")
    return "\n".join(parts)


async def _deliver(rec: "SessionRecord") -> None:
    """Entrega el resultado por los raíles de siempre: proactive (voz+UI) + nota [SISTEMA] + memoria (único
    escritor). Réplica del antiguo dispatch._deliver, ahora por-sesión."""
    summary = operator_safe_summary(rec.result_summary)
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
