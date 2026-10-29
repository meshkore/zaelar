"""What a worker session does with each EVENT of its backend: phase, steps, notes, usage, the context warning,
the web hand-off, the permission gate and the search relay. Part of nucleo.workers.session (names through _s)."""
from __future__ import annotations

from loguru import logger
import asyncio
import time

from nucleo.workers import session as _s


def _on_event(self, ev) -> None:
    rec = self._rec
    d = ev.data or {}
    if ev.type == "spawned":
        rec.native_sid = d.get("native_session_id") or rec.native_sid
        self._model = d.get("model") or self._model
        self._emit_meta_row()                              # V2-048: fila "worker · <backend>" con modelo + capa
    elif ev.type == "phase":
        _lbl = (d.get("label") or "").strip()
        self._tool_phase = _lbl or getattr(self, "_tool_phase", None)   # what THIS tool call says it is doing
        rec.phase = _lbl or rec.phase
        self._bus("worker.phase", {"id": rec.task_id, "phase": rec.phase})
        # THE DIARY THE OPERATOR WATCHES: the PROCESS tab read only `hbnote` entries, while `progress.phrase`
        # stayed in `rec.phase`. Session `ed9df756`: fourteen browser steps, two diary entries, 2.5 min of «working».
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
        _n = _s._stall.spin_count(self._spin, d.get("action", ""), d.get("target") or "")
        if _n == _s._stall.SPIN_WARN:
            asyncio.create_task(self._say_deliver_now(_n, str(d.get("target") or "")[:80]))
        elif _n >= _s._stall.SPIN_KILL:
            self._spin_dead = True
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
        if getattr(self, "_tool_phase", None) and rec.phase == self._tool_phase:
            rec.phase, self._tool_phase = _s._default_label(rec.kind), None   # V2-831: the call returned, «reading X» is over
        _s._stall.spin_result(getattr(self, "_spin", None), d.get("text"))   # a new answer to the same step is progress
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
        # V2-713 R4 — THE LABEL SAYS WHICH FAULT: «proveedor sin cuota» was shown for credential and request
        # rejections too, whose fixes are opposite. The cause comes classified from `providers.note_failure`.
        rec.provider_down = {"provider": d.get("provider") or "", "next": d.get("next") or "",
                             "kind": d.get("kind") or "", "text": d.get("text") or ""}
        titulo = {"exhausted": "proveedor sin cuota", "auth": "credencial rechazada",
                  "broken": "el proveedor RECHAZA nuestras peticiones"}.get(
                      str(d.get("kind") or ""), "proveedor caído")
        self._emit_chip(titulo, (d.get("provider") or "") +
                        (f" → relevo a {d['next']}" if d.get("next") else " · sin relevo"), ok=False)
    elif ev.type == "progress":
        self._bus("worker.progress", {"id": rec.task_id, "pct": d.get("pct"), "note": d.get("note")})
    elif ev.type == "usage":
        # PARTIAL USAGE per message (2026-08-13): covers a worker KILLED by budget, which never emits `result`.
        # Not added to `result`'s total (already summed), kept as the declared MINIMUM. See `_finish`.
        u = d.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            try:
                self._usage_partial[k] = self._usage_partial.get(k, 0) + int(u.get(k) or 0)
            except (TypeError, ValueError):
                pass
        self._model = d.get("model") or self._model
        self._base_url = d.get("base_url") or self._base_url
        # THE NUMBER THAT PREDICTS DEATH (incident 2026-08-18): `ctx_tokens` is the LAST request's size, unlike the
        # accumulated `_usage_partial`. Past the budget the still-alive worker gets ONE turn to deliver what it has.
        rec.real_model = d.get("real_model") or rec.real_model
        ctx = int(d.get("ctx_tokens") or 0)
        if ctx:
            rec.ctx_tokens = ctx
            self._maybe_warn_context(ctx)
    elif ev.type == "result":
        rec.result_summary = str(d.get("summary") or "").strip()
        rec.ok = bool(d.get("ok", True))
        rec.error_class = str((d.get("data") or {}).get("error_class") or rec.error_class or "")
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


def _maybe_warn_context(self, ctx: int) -> None:
    """Nearing the context ceiling → ask the worker, ONCE, to deliver what it already has (incident 2026-08-18).

    Why talk to it instead of killing it: the session is ALIVE and its own reasoning is the cheapest possible
    summary of its progress — far better than anything we could reconstruct from `steps`/`plan` afterwards. It is
    the same stdin injection channel `send_to_worker` already uses, so no new machinery. Best-effort throughout:
    failing to warn must never be what breaks a task that is still working."""
    rec = self._rec
    if self._ctx_warned or _s._CTX_BUDGET <= 0 or ctx < _s._CTX_BUDGET:
        return
    self._ctx_warned = True
    logger.warning(f"worker[{rec.task_id}]: contexto en {ctx} tokens (tope {_s._CTX_BUDGET}) → pido entrega")
    self._emit_chip("contexto casi lleno", f"{ctx} tokens — pidiendo entrega", ok=False)
    try:
        from voice.observer import emit
        emit("task", "⚠️ contexto casi lleno", text=f"{ctx} tokens — le pido que entregue lo que tiene",
             extra={"id": rec.task_id, "src": f"worker:{rec.task_id}", "ctx_tokens": ctx})
    except Exception:
        pass
    asyncio.create_task(self._ask_for_delivery())


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


def _maybe_unstick_permission(self, d: dict) -> None:
    raw = " ".join(str(d.get(k) or "") for k in ("text", "result", "output", "target"))
    txt = raw.lower()
    if not txt or not any(n in txt for n in self._DENIED_NEEDLES):
        return
    if self._perm_hits >= self._PERM_MAX:
        return
    self._perm_hits += 1
    last = self._perm_hits >= self._PERM_MAX
    self._rec.perm_denied = _s.denied_fragment(raw) or self._rec.perm_denied
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


def _relay_search(self) -> None:
    """The provider's built-in search is out of quota: tell THIS worker, once, to use Zaelar's (2026-09-28).

    Blindness was detected and announced, and nothing changed for the worker: it kept calling the dead tool
    or reasoning without material (demo pass 30 — Z.ai's web reader answering 429 while the model worked).
    The operator's rule: the provider's own search first while it works, OURS when its quota runs out — the
    same search the FlashBrain uses, reached through the per-task bridge. The spawn prompt already names both;
    this is the moment the second one becomes the only one, delivered on the worker's next bridge contact."""
    if getattr(self, "_search_relayed", False):
        return
    self._search_relayed = True
    try:
        from nucleo.workers.providers.claude import bridge_python
        py = bridge_python() or "python"
    except Exception:  # noqa: BLE001
        py = "python"
    msg = ("Tu buscador integrado se ha quedado SIN CUOTA y no vuelve en esta tarea: no lo uses más. Busca "
           f"con el de Zaelar: `{py} -m nucleo.cli.bridge act use_tool \"<qué buscas>\"` — la consulta entre "
           "comillas, sin llaves ni ficheros. Para leer una página, el navegador: "
           f"`{py} -m nucleo.cli.nav`.")
    try:
        import asyncio as _aio
        _aio.get_running_loop().create_task(self.inject(msg))
    except RuntimeError:
        self._rec.injects.append(_s.Inject(text=msg, ts=time.time()))   # no loop: the bridge piggyback still delivers it
    try:
        from voice.observer import emit
        emit("task", "🔁 búsqueda → la de Zaelar (cuota del proveedor agotada)", role="system",
             extra={"id": self._rec.task_id, "span": f"worker:{self._rec.task_id}"})
    except Exception:  # noqa: BLE001
        pass
