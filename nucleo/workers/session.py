"""nucleo/workers/session.py — `WorkerSession`: a live Brain Worker session (V2-038).

Wraps a `WorkerBackend` and drives its lifecycle: starts the engine, PUMPS its normalized events
(`WorkerEvent`) → updates the IN-MEMORY RECORD (source of truth, §v2·C) + publishes on the bus (`worker.*`) + emits
the activity chip + DELIVERS the result through voice+UI. Manages the **injection queue** (↓, §v3·H: pending→
delivered, no double delivery) and **courteous shutdown** (group kill, §v2·D).

The session does NOT speak to the user directly or resolve `ask`/`act` (that is the worker_api request/response
plane + supervisor loop): here we only pump the backend stream (spawned/phase/result/error/done) and keep the record
consistent. Design: initiatives/V2-038-brain-workers-interactivos.md.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field

from loguru import logger

from . import progress as _progress
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
    """The ROW for a live session in the in-memory record (source of truth). Absorbs what was previously scattered
    across escalate._tasks / dispatch._INFLIGHT / dispatch._SESSIONS (§v3·G). The serializable projection is provided
    by `dispatch.active_sessions()`; handles (session/task) do not travel to STATE or /api/tasks."""
    task_id: str
    goal: str
    title: str = ""               # V2-530 — the NAME, beside the BRIEF; readers fall back to `goal`
    kind: str = "generic"
    backend: str = ""
    label: str = ""
    phase: str = "en cola"
    status: str = "queued"        # queued | running | done | error | cancelled
    started: float = field(default_factory=time.time)
    native_sid: str = ""
    waiting_on: str = ""          # "" | "user" | "flash"  (lo fija worker_api al aparcar un ask)
    ask: str = ""                 # text of the active question (if waiting_on)
    ask_corr: str = ""            # corr_id of the active ask
    result_summary: str = ""
    ok: bool = True
    parent_task_id: str = ""
    depth: int = 0
    trace_id: str = ""            # V2-044: trace of the phrase that originated the session (chains all its events)
    nav_task: str = ""            # kind=web: associated browser task ID (card) — set by dispatch
    # V2-259 — the SHEET for this errand (`results::<sheet>`), sealed ONCE by `dispatch._sheet_open`. It is not
    # `task_id` alone, and that was a real defect: `escalate._seq` starts at 0 in each process, so IDs
    # REPEAT across restarts and the first errand of a new startup landed in the previous session's
    # `results--1` sheet — which `begin_task(fresh=True)` opens anew, that is, DELETES. Exactly the «search deletion
    # error» this initiative exists to remove, reintroduced through the back door.
    sheet: str = ""
    # V2-227 — WHERE the operator will see the result, decided when ASSIGNING it and not when delivering it. CLOSED
    # vocabulary (`nucleo/surfaces.py`): list | item | widget | voice | silent. It is sealed ONCE (`set_once`) and
    # not reconsidered midway: changing surfaces when the operator is already looking at the first is worse than
    # having chosen incorrectly. Empty = not sealed yet (for example, a session created manually in a test).
    surface: str = ""
    # V2-227 scope C — the HISTORY of readable phases, for the sheet's PROCESS tab. Short ring: it is
    # what the operator is looking at now, not an audit log (that already lives in observability). It is kept
    # separate from `steps`, which are the raw steps derived from the stream and are shown to nobody.
    phases: list = field(default_factory=list)     # [{"t": <ts>, "s": "entrando en booking.com"}]
    last_event_at: float = field(default_factory=time.time)
    injects: list = field(default_factory=list)     # [Inject]
    paused: bool = False           # V2-065: SIGSTOP'd (⏻ del operador) — sigue "running" para el registro, pero
                                    # frozen; do not confuse with status=cancelled (that is irreversible)
    # ── observabilidad ESTRUCTURADA del worker (V2-059) ──────────────────────────────────────────────────────
    # The worker opens a Claude Code session with opaque INTERNAL work. To view it in a controlled way:
    #  · `plan`  = the list of tasks the worker DECLARES at startup (`hbnote plan "a|b|c"`).
    #  · `done`  = how many plan steps it has completed (`hbnote progress --done N`) → progress = done/len(plan).
    #  · `pct`   = explicit 0-100 progress if reported (takes precedence over done/plan); -1 = derive/unknown.
    #  · `note`  = latest readable progress note.
    #  · `steps` = ring of the latest REAL steps (derived from the stream: tool + where + what) → debug + UI.
    plan: list = field(default_factory=list)
    done: int = 0
    pct: int = -1
    note: str = ""
    steps: list = field(default_factory=list)
    # BREADTH of an investigation (`hbnote considered N --kept M`): how many candidates the worker REALLY
    # examined before keeping M. This is what separates a defensible selection from the first three search-result
    # rows, and lets the brain offer «I've seen 47; is that enough, or should I continue?» instead of hiding the fact.
    # -1 = not reported (a task that is not an investigation, or a worker that did not say).
    considered: int = -1
    kept: int = -1
    # Died because the PROVIDER ran out of quota (not because of the task) → `{provider, next, text}`. The
    # backend sets it when it sees the error; `_finish` uses it to retry ONCE with the handoff tier instead of
    # delivering the operator an «API Error … Weekly Limit Exhausted» as though it were the report.
    provider_down: dict | None = None
    provider_retried: bool = False
    # Died (or is about to) because the CONTEXT no longer fits, not because the provider failed (incident
    # 2026-08-18). A separate family on purpose: relaying to another provider does not fix a blown context — the
    # next one blows up identically — so this puts NOBODY on cooldown: it COMPACTS AND CONTINUES with what was learned.
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
    # V2-238 — A HANDOFF IS NOT A DEATH. When one of `_finish`'s two deliveries completes (provider handoff,
    # compact-and-continue), this session has not failed: it has PASSED THE BATON to another that is already
    # running. Without this fact, `ok=False` made it indistinguishable from a dead worker, and the engine told the
    # operator that their task «DIED without a result and will not be retried automatically» while the handoff worked.
    handoff: str = ""             # "" = genuinely final · otherwise, where the baton went, in readable form
    # V2-241 — the exact FRAGMENT the gate stopped (`cd /Users/…`, `curl -s https://…`). It is stored so it can be
    # named in the correction —a general rule does not say which of its commands is unnecessary— and so a final
    # without delivery can say why it was left incomplete instead of staying silent.
    perm_denied: str = ""
    ctx_tokens: int = 0             # context size of the last message (for the panel and the watchdog)
    real_model: str = ""            # the model that ACTUALLY ran, when the provider says so (≠ requested alias)
    # runtime handles (NOT serialized):
    session: "WorkerSession | None" = None
    task: "asyncio.Task | None" = None


    # V2-241 — WHICH fragment the gate stopped. A correction repeating general rules does not say WHICH command
    # is unnecessary; the CLI names it in three different measured forms. Returns "" if the text does not say —
    # never invents a fragment, which would ask it to rewrite a command it did not write.
_DENIED_RE = (
    re.compile(r"following part requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"\bcd in ['\"](.+?)['\"] was blocked", re.I),
    re.compile(r"requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"permissions? to use\s+(\S+)", re.I),
)


def denied_fragment(text: str) -> str:
    """The command (or path) named by the gate, trimmed and placed on one line."""
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
        self._model = spec.model or ""     # V2-048: worker model (observability chip) — refined by `spawned`
        self._usage: dict = {}             # `result` tokens (input/output) → size chip in the final row
        self._usage_partial: dict = {}     # tokens ACCUMULATED message by message: all we have if we kill it
        self._cost = None                  # USD cost of `result` → final-row text (informational, NOT used for
                                            # used for Energy — see energy_meter.report_worker_usage docstring)
        self._base_url = ""                # actual endpoint of the tier serving the session (energy_meter, 2026-08-05)
        self._started_at = time.time()     # to measure the worker's FIRST output (its TTFT) — see _emit_note
        self._first_output_at = 0.0
        # V2-241 — permission correction ran ONCE per session (V2-211), and the measured worker hit the gate THREE times.
        # From the second hit onward nobody told it anything and it died silently, exactly what the network
        # intended to prevent. Now every hit is corrected up to a cap, and the LAST one changes its message.
        self._perm_hits = 0
        self._ctx_warned = False           # the wrap-up turn is injected ONCE (incident 2026-08-18): repeating it
                                            # every message past the budget would spend the little room that is left

    @property
    def alive(self) -> bool:
        return self._b.alive and not self._stopped

    # ── complete session lifecycle ──────────────────────────────────────────────────────────────────────────
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
            logger.warning(f"worker[{rec.task_id}]: run failed: {e}")
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
            # THE DIARY THE OPERATOR WATCHES. This line was missing, and its absence did not look like a failure: the
            # PROCESS tab read a ring (`rec.phases`) populated only by `hbnote`, meaning whatever the worker
            # bothered to narrate. Everything that translates ITS STEPS into a sentence —`progress.phrase`, the
            # component written precisely for this— stayed in `rec.phase` (a single line, the NOW line) and died there.
            # Measured in session `ed9df756`: fourteen real browser steps and two diary entries, both at the end.
            # The operator saw «working» for two and a half minutes.
            try:
                from nucleo import dispatch as _d
                _d.record_phase(rec.task_id, _lbl)   # THE LABEL THAT ARRIVES, not `rec.phase`: empty means
                #  «another source supplies the phase» (`hbnote`, richer), and recording the previous one would
                #  repeat in the diary a step that has not happened again.
            except Exception:  # noqa: BLE001
                pass
            if not d.get("quiet"):                             # quiet = accompanies a rich `step` → do not duplicate row
                self._emit_chip("phase", rec.phase)
        elif ev.type == "step":
            self._emit_step(d)                                 # V2-048: concrete WHERE + WHAT of this step
            # V2-059: besides the panel row, STORE the step in the record (ring, cap 12) → /api/tasks + STATE
            # see the worker's REAL activity (not only the coarse phase). _tool_step composes where/what.
            try:
                rec.steps.append({"where": d.get("where", ""), "action": d.get("action", ""),
                                  "target": (d.get("target") or "")[:80], "ts": time.time()})
                if len(rec.steps) > 12:
                    rec.steps = rec.steps[-12:]
            except Exception:
                pass
        elif ev.type == "step_result":
            self._emit_step_result(d)                          # 2026-08-10: what ANSWERED that step
            self._maybe_unstick_permission(d)                  # V2-211: did it hit OUR own gate?
            self._maybe_hand_web(d)                            # V2-236: what the SEARCH brought to the conversation
        elif ev.type == "note":
            self._emit_note(str(d.get("text") or ""))          # worker narration → observability, not voice
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
            # PARTIAL USAGE, message by message (2026-08-13). It is accumulated separately from the `result`'s
            # `usage` because it covers a case `result` cannot: a worker KILLED by budget never emits it. It is not
            # added to the final total if `result` arrives —the CLI has already summed that— but is preserved as
            # the declared MINIMUM. See `_finish`.
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
            # (if a backend emits it explicitly) → the loop reports it; here it only goes to the bus.
            self._bus("worker.say", {"id": rec.task_id, "text": (d.get("text") or "")[:400]})
        elif ev.type == "error":
            rec.ok = False
            if d.get("fatal") and not rec.result_summary:
                # the operator must HEAR that it failed (never silence): _finish delivers this summary via voice+UI.
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
                    "sheet": str(getattr(rec, "sheet", "") or ""),   # the sheet belongs to the ERRAND, not the session
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
        # PROVIDER HANDOFF: the task did not fail; it ran out of fuel. Relaunch ONCE —the exhausted tier is already
        # on cooldown, so the new spawn takes the next one— instead of delivering the operator the provider's raw
        # error as though it were the result of what they requested.
        if (rec.provider_down and not rec.provider_retried and rec.status != "cancelled"
                and rec.relay_gen < self._RELAY_CAP):
            rec.provider_retried = True
            nxt = rec.provider_down.get("next") or ""
            if nxt:
                try:
                    from nucleo.flash import escalate as _esc
                    _esc.escalate_to_slowbrain(rec.goal, context={
                        "src": "provider_failover", "kind": rec.kind, "trace": rec.trace_id,
                        "sheet": str(getattr(rec, "sheet", "") or ""),   # the sheet belongs to the ERRAND, not the session
                        "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
                    rec.result_summary = ""          # sin entrega: la retoma el worker de relevo, sin ruido
                    rec.ok = False
                    rec.handoff = f"proveedor sin cuota → relevo a «{nxt}»"
                    logger.warning(f"worker[{rec.task_id}]: proveedor sin cuota → relanzada con «{nxt}»")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"worker[{rec.task_id}]: relevo de proveedor falló: {e}")
                    rec.ok = False
                    rec.result_summary = ("Me he quedado sin cuota en el proveedor de los procesos de fondo y no "
                                          "he podido relevarlo. Míralo en el panel de estado.")
            else:
                # V2-238 — THE THREE PATHS THAT ARE NOT A HANDOFF CLOSE `ok`. The three branches above write a
                # `result_summary` that ANNOUNCES a failure, and none touched `ok`, which starts as True. If the
                # backend had not already closed it, that sentence was delivered as «Task completed: I ran out of quota…»
                # —the exact defect targeted by V2-092/V2-236: an ending that says the opposite of what happened.
                rec.ok = False
                rec.result_summary = ("Me he quedado sin cuota en el proveedor que mueve mis procesos de fondo y "
                                      "no tengo otro configurado, así que esta tarea se queda parada. Lo tienes "
                                      "en el panel de estado.")
        # THE CHAIN STOPPED: it must be said, and the TRUTH must be told. Without this, a capped ending retained the
        # provider's raw error in `result_summary`, and `operator_safe_summary` translated it as «I ran out of context…
        # I'LL RESUME it with what I had» —a retry promise that will no longer happen. A reassuring sentence that
        # lies is worse than the raw error: the operator waits for something nobody is doing, the V2-185 defect at
        # another gate.
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

        # V2-241 — A SILENT ENDING AFTER HITTING THE GATE. The three measured cases died without saying anything,
        # and the cause appeared only by cross-checking the engine log. If the session ends without delivery or
        # handoff but hit our own gate, THAT is what happened, and it is what the operator must hear: it is not a
        # task failure; the route they chose is closed here.
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
        # DELIVERY through voice+UI + [SYSTEM] + memory, except on cancellation (the operator already knows they stopped it).
        if rec.status != "cancelled" and rec.result_summary.strip():
            await _deliver(rec)
        self._bus("worker.done", {"id": rec.task_id, "ok": rec.ok, "status": rec.status})
        # TOKENS ARE ALWAYS CHARGED, even if the session was CANCELLED (2026-08-13). This lived inside the
        # `if rec.status != "cancelled"` below, which exists for an INTERFACE reason (do not paint two contradictory
        # `end` rows) and swept away an unrelated BILLING concern: a worker killed by budget had consumed REAL tokens
        # and was metered at ZERO. Measured in the database: 704 s, 256 steps, ~$0.20 of xAI tokens → €0 billed.
        # Two distinct concerns in one `if`; they are separated.
        u = self._usage or self._usage_partial or {}
        pt, ct = u.get("input_tokens"), u.get("output_tokens")
        # CACHED input is a SEPARATELY BILLABLE LINE and does not belong in `input_tokens` (Anthropic-shaped usage
        # has the three counters separated). In a long agent session the same prompt prefix is reread each turn,
        # so cache tokens end up being SEVERAL TIMES the fresh-input tokens: measured against the cost reported by
        # Grok's own CLI, ignoring them left 29% of the bill out (211k cached versus 74k input). It is passed to the
        # meter, which tariffs it at its own price.
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
        # a CANCELLED session has already emitted its end chip (ok=False) from dispatch.cancel_session — re-emitting
        # here produced TWO contradictory ends (ok=False and ok=True one second later, seen in the 2026-07-14 demo).
        if rec.status != "cancelled":
            # V2-048: the final row carries TOKENS (size chip) + COST + the model — what the task cost.
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
            # AN ENDING SAYS WHY (V2-237, 2026-08-21). The ending row showed cost and nothing else, so a DEAD worker
            # left `text:""` and the reason had to be found by cross-checking the engine log through `span=worker:N`.
            # Measured by the harness in `best-plumber-same-day`: the only error events in the round were from the
            # worker that did NOT die, and the four that did die said nothing. An ending without a cause
            # reads the same as a normal ending.
            #
            # The RAW text is intentional: this row belongs to the record, not the operator's mouth. Ensuring a provider error
            # being read aloud is handled by `operator_safe_summary` during delivery, and its own docstring says
            # the full text remains in the log —which is exactly this.
            extra["status"] = str(rec.status or "")
            if rec.handoff:
                # V2-238 — if the BATON WAS PASSED, the row says so by name. A handoff delivered here the same
                # empty ending as a dead worker (`result_summary` is deliberately emptied so the operator does not
                # see two deliveries), so both read the same in the record.
                extra["handoff"] = rec.handoff
                lbl = f"{lbl} · relevada: {rec.handoff}".strip(" ·")
            elif not rec.ok:
                why = " ".join(str(rec.result_summary or "").split())[:200]
                lbl = f"{lbl} · {why}".strip(" ·") if why else (lbl or str(rec.status or "sin completar"))
            self._emit_chip("end", label=lbl, ok=rec.ok, extra=extra)
        # LEAK FIX (marathon 2026-07-22/23): `run()` sale del bucle en el PRIMER "done" (= primer `result` de
        # stream-json), but the `claude --print` process remains alive (multi-turn mode, waiting for more stdin).
        # dispatch performs `_SESSIONS.pop(key)` immediately after `run()` → the ONLY reference to the backend is
        # lost without killing the process: it remained orphaned forever (observed: 14 zombie processes after ~2h).
        # If the session was not already closed by `stop()` (explicit cancellation), close the backend here before releasing it.
        if not self._stopped:
            try:
                await self._b.stop()
            except Exception:
                pass

    # ── injection (↓) ───────────────────────────────────────────────────────────────────────────────────────
    async def inject(self, text: str) -> None:
        """Queues an instruction for the worker (§v3·H). PRIMARY delivery = piggyback (worker_api serves it on the
        bridge's next contact); SECONDARY = backend stdin (conversational engines)."""
        text = (text or "").strip()
        if not text:
            return
        self._rec.injects.append(Inject(text=text, ts=time.time()))
        try:
            await self._b.send(text)     # secondary path; if the backend queues until the turn ends, nothing happens
        except Exception:
            pass

    def take_pending_injects(self) -> list[str]:
        """Returns pending injections and marks them `delivered` (idempotent, no double delivery). Called by
        worker_api when responding to a bridge (piggyback)."""
        out = []
        for inj in self._rec.injects:
            if inj.state == "pending":
                inj.state = "delivered"
                out.append(inj.text)
        return out

    # ── courteous shutdown ─────────────────────────────────────────────────────────────────────────────────
    async def stop(self, *, grace: float = 3.0, reason: str = "operator") -> None:
        if self._stopped:
            return
        self._stopped = True
        self._rec.status = "cancelled"
        try:
            await self._b.stop(grace=grace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: backend stop failed: {e}")
        self._bus("worker.cancelled", {"id": self._rec.task_id, "reason": reason})

    # ── V2-065: pause ≠ stop (see workers/base.py) — freezes without setting `status="cancelled"` ───────────
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
        """At birth: which ENGINE + MODEL + LAYER drives this task (what the operator asked it uses)."""
        try:
            from voice.observer import emit
            rec = self._rec
            model = self._model or self._spec.model or "(def)"
            emit("worker_start", f"worker · {rec.backend or self._b.name}", text=rec.goal[:120],
                 extra={"id": rec.task_id, "model": model, "layer": rec.kind})
        except Exception:
            pass

    def _emit_note(self, text: str) -> None:
        """What the worker IS SAYING while it works (its reasoning aloud), with the session ID and the
        `worker` marker so the viewer reads “this comes from brain worker N”. This row fills the gap
        between birth and action: it appears as soon as the model emits the text block, without waiting for a tool.

        It also measures the **first output** (`first_output_ms` since the session started)—the equivalent of TTFT
        for a voice turn, so we can tell whether a worker was slow because the engine starts slowly or because the
        work was genuinely long."""
        t = " ".join((text or "").split())
        if not t:
            return
        ms = None
        if not self._first_output_at:
            self._first_output_at = time.time()
            ms = round((self._first_output_at - self._started_at) * 1000)
        _progress.narration_out(self._rec.task_id, self._model or "", t, ms)

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

    # V2-211 — THE GATE IS OURS, and the worker dies there without saying so. Three cases measured on the same day,
    # three different commands, the same pattern: `cd … was blocked`, `requires approval: curl -s …`, `requires
    # approval: cd /Users/…`. In headless mode nobody approves, so the approval request is a dead end; the worker
    # reads it as a no and stops, while the turn continues to count as progress.
    #
    # `dispatch_prompts` attacks it upstream (the drawer rules, like the interpreter on 2026-08-02); this is the
    # NET: if it still hits the gate, it is told IMMEDIATELY what happened and how to rewrite it. The same form as
    # the early delivery above —one injected turn, ONCE— because the session is still alive and its own reasoning
    # is the shortest route back.
    _DENIED_NEEDLES = ("requires approval", "was blocked", "permission to use", "requested permissions",
                       "may only change directories")

    def _maybe_hand_web(self, d: dict) -> None:
        """What a WEB SEARCH returns goes to the conversation immediately, not when the worker delivers.

        Here rather than in each backend: `where` is already normalized by the substrate (`_PLACE`), so this covers
        Claude Code, Codex, and Grok in one place — including each CLI's NATIVE tools, where the harness measured the
        useful data being lost. An `is_error` is not pushed: a tool failure is not a finding, and already
        tiene su propio camino (`_maybe_unstick_permission`, el chip del panel).
        """
        try:
            if str(d.get("where") or "") != "web" or d.get("is_error"):
                return
            from nucleo.workers import findings
            findings.hand_web_finding(self._rec.task_id, str(d.get("text") or ""), self._rec.goal)
        except Exception:  # noqa: BLE001
            pass

    _PERM_MAX = 3          # the number the harness measured in one worker before it died silently

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
        # V2-241 — the LAST warning does not repeat the rules: if three rewrites were insufficient, continuing to
        # correct it is asking the same thing for a fourth time. What is needed is for it to DELIVER what it has
        # before dying, which is the difference between an incomplete task and a silent task.
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
        """A STEP: WHERE it works (badge/category by place) + WHAT it does and on what (action + target)."""
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
        """The step's EVIDENCE: what the tool answered (2026-08-10).

        The stream's `tool_result` entries were discarded as «internal noise», taking with them the only thing that lets
        to audit a worker properly: we could see that it searched a place and opened a URL, **never what it found**. A
        a worker that brings junk and one that brings the exact datum left THE SAME trace. It is trimmed (not summarized —
        a summary is an interpretation) and in the same family as its step, so it reads continuously: I ask → I
        receive an answer."""
        try:
            from voice.observer import emit
            body = str(d.get("text") or "").strip()
            if not body:
                return
            where = (d.get("where") or "sistema")
            place, kind = _PLACE.get(where, _PLACE["sistema"])
            from nucleo.workers.probes import is_menu_probe   # see its docstring: reading the menu is NOT a crash
            bad = bool(d.get("is_error")) and not is_menu_probe(body)
            _ex = {"id": self._rec.task_id, "tool": d.get("tool") or "", "evidence": True,
                   "is_error": bad, "span": f"worker:{self._rec.task_id}"}
            if bad and d.get("cmd"):
                _ex["cmd"] = str(d["cmd"])[:220]     # WHAT was attempted, not only what went wrong (see claude_session)
            emit(kind, place + (" ⚠️ error" if bad else " ↩"), text=body, extra=_ex)
            # BLINDNESS: a quota error in the provider's TOOLS does not fail the model call, so it does not trigger
            # handoff and the worker keeps reasoning WITHOUT being able to search. Without this there was neither
            # alert nor trace: the worker appeared healthy and delivered conclusions without evidence. See
            # `providers.note_tool_blindness`.
            if bad:
                try:
                    from nucleo.workers import providers as _prov
                    _prov.note_tool_blindness(body, tool=str(d.get("tool") or ""),
                                              provider=str(d.get("provider") or ""))
                except Exception:
                    pass
        except Exception:
            pass


# Worker's location → (panel label, `kind` fixing the CATEGORY/filter and color). Reuses known kinds from
# (observer._CAT): memory→memory (purple, Memory filter), browser→browser (Browser filter),
# web→search, code/file/zaelar/system→task (main). Thus worker steps integrate into the SAME filters as first-class
# events, rather than a separate drawer (V2-048).
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


# V2-276 — the two text builders (`operator_safe_summary`, `context_handoff`) have lived in
# `handoff.py` since 2026-08-24 (architectural ratchet). Pure, operating only on the record; this
# file governs a session's LIFECYCLE, it does not compose text. They are re-exported because tests and
# `providers.py` refer to them from here.
from nucleo.workers.handoff import (  # noqa: F401,E402 — re-export
    context_handoff, operator_safe_summary,
)

async def _deliver(rec: "SessionRecord") -> None:
    """Delivers the result through the usual rails: proactive (voice+UI) + [SYSTEM] note + memory (sole
    writer). Replica of the former dispatch._deliver, now per session."""
    summary = operator_safe_summary(rec.result_summary)
    if not summary:
        return
    try:
        from voice import brain_notes
        head = "Tarea completada" if rec.ok else "Tarea sin completar"
        brain_notes.push(f"[SISTEMA] Brain worker · {head}: {summary[:400]}")
    except Exception:
        pass
    # MEMORY: only SUCCESS is remembered as a durable result (2026-07-14 audit — the P2 refactor lost the one-shot
    # `ok` gate and FAILED tasks wrote mid-sized pills such as «I could not complete the task», creating noise that
    # also competed in recall). Failure already reaches the operator through voice + [SYSTEM] note. Provenance is
    # stamped (`meta.source`) so it can be audited/cleaned by origin.
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
