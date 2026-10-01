"""nucleo/workers/session_notes.py — what a worker session SAYS and SHOWS while it runs (V2-778 F1, 2026-10-01).

The worker's chips, notes, step rows, step results and the permission/delivery explanations it gives the
operator. Moved out of `nucleo/workers/session.py` (859 lines, over its size ceiling) as a mixin: the methods are
the SAME code, `WorkerSession` inherits them, and `session._PLACE` is re-exported for the callers that read it.
They reach the session only through `self` (its record, its bus, its backend) — no state of their own.
"""
from __future__ import annotations

import time

from loguru import logger

from . import progress as _progress

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


class SessionNotes:
    """Mixin for `WorkerSession`: the session's mouth and its timeline rows."""

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

    async def _say_deliver_now(self, n: int, target: str) -> None:
        """The spin warning (stall.SPIN_WARN): the same step `n` times — deliver, do not probe again."""
        try:
            await self._b.send(
                f"AVISO DEL SISTEMA: llevas {n} veces seguidas el mismo paso («{target}») sin avanzar. Para. "
                "Entrega AHORA lo que ya tengas por el camino de entrega habitual y di qué te ha faltado; si "
                "repites ese paso más veces, la tarea se cerrará sin tu entrega.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: no pude avisar del bucle: {e}")

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
                    if _prov.note_tool_blindness(body, tool=str(d.get("tool") or ""),
                                                 provider=str(d.get("provider") or "")):
                        self._relay_search()
                except Exception:
                    pass
        except Exception:
            pass
