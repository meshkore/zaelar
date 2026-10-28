"""The pulse's slower revisits (confirmations, the harness, abandoned flows) and the phrases it speaks with."""
from __future__ import annotations

import os

from loguru import logger



class FlowsPulse:
    async def _supervise_confirms(self, now: float) -> None:
        """A pending irreversible-action confirmation the operator never answered must not die in silence
        (2026-08-16, operator request after a diagnosed real incident: two turns asked the same "delete all my
        agenda data" confirmation on the same widget — split by the segmenter — and both sat stuck with no way
        to answer either one, and no signal that anything had gone wrong). `widgets/confirm.py` already closes
        the orphaned/expired confirmation's flow synchronously (so the observability viewer stops showing it "EN CURSO"
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

    async def _supervise_harness(self, now: float) -> None:
        """V2-660 — re-verify the open errand goals against the product's own state: a goal a worker (or a
        later turn) met is CLOSED here with an event, an expired one is retired. No voice: the delivery
        that met it already announced itself (V2-644); this is the ledger catching up, not a second mouth."""
        try:
            from nucleo.circuit import harness
            if harness.open_goals(now):
                await harness.sweep(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"harness sweep skipped: {e}")
        # V2-776 L3 — the circuit's ledger (inline actions and errands alike), re-verified here; met ones close
        # with their event. No voice: the ending that meets a spec speaks for itself.
        try:
            from nucleo import circuit as _circuit
            _circuit.tick(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"circuit tick skipped: {e}")

    async def _supervise_stale_flows(self, now: float) -> None:
        """Closes a CONVERSATIONAL flow the operator started and then walked away from (2026-08-16, operator
        request after a diagnosed real incident — the observability viewer kept showing several "en curso" flows from a
        session the operator had abandoned minutes earlier). `_maybe_close_flow` (the per-turn path in
        `voice/engine/llm/providers/nucleo.py`) only ever gets ONE chance to close a flow, right when its own
        turn finishes; if that turn correctly deferred (an accumulator chain, a pending confirmation, a live
        worker), nothing EVER revisits the decision once those conditions clear on their own. This is that
        revisit — on a slow, deliberately-throttled timer, never the 1Hz tick itself (a real SQL query, not
        RAM bookkeeping).

        Invariant demanded by the operator, verbatim: "if it is an active search that keeps a Brain Worker
        running, it must NEVER be closed until it finishes — the ball is in the people's court." `dispatch.has_live_trace` is checked FIRST and is the one condition that can NEVER be
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
                    continue                                       # no trace, or already explicitly closed
                last_ms = float(f.get("last_ms") or 0)
                age = now - last_ms / 1000.0
                if age < self._stale_flow_secs:
                    continue                                       # still within the grace window
                if _disp_stale.has_live_trace(corr_id):
                    continue                                       # a live worker is NEVER closed due to time
                if corr_id in confirm_trace_ids:
                    continue                                       # waiting for the operator's yes/no
                with _trace_stale.scope(corr_id):
                    _emit_stale("flow", "end", role="system",
                                extra={"ok": True, "reason": "stale_no_input", "idle_s": int(age)})
        except Exception as e:  # noqa: BLE001 — a failure here never brings down the loop
            logger.warning(f"loop: supervise_stale_flows failed (ignored): {e}")

    @staticmethod
    def _lang():
        """The active language catalog (`voice.engine.core.langs`) — falls back to Spanish if the import fails."""
        try:
            from voice.engine.core import langs
            return langs.current_language()
        except Exception:
            class _Fallback:
                worker_ask_named = "Oye, el proceso «{goal}» pregunta: {question}"
                worker_ask_generic = "Oye, uno de los procesos en marcha pregunta: {question}"
                worker_budget_killed = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                       "encontrado hasta ahora.")
                worker_end_state_met = "Aun así, lo que pediste sí quedó hecho: lo he comprobado."
                worker_end_state_unmet = "Lo que pediste no quedó hecho: queda {missing}."
                worker_end_state_unverifiable = "No he podido comprobar si lo que pediste quedó hecho."
                worker_timeout_running = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
                worker_stuck = ("El proceso «{goal}» lleva {minutes} minutos sin dar señales. Si no reacciona en "
                                "un par de minutos lo reinicio una vez.")
                confirm_expired = ("Dejé de esperar tu confirmación sobre: {question} Dímelo otra vez si quieres "
                                   "que lo haga.")
                generic_task = "la tarea"
            return _Fallback()

    async def _deliver_keyed(self, title: str, text: str, key: str) -> None:
        """Deliver with a retractable KEY (V2-353), allowing a two-argument injected `deliver`.

        The test double is injected as `async def deliver(title, text)`, and only two notices in the loop need
        this key: fall back to the old signature instead of requiring every caller to change.
        """
        try:
            await self._deliver(title, text, key=key)
        except TypeError:
            await self._deliver(title, text)

    def _say(self, template: str, **kw) -> str:
        """SPOKEN phrase initiated proactively (worker questions, timeouts…) in the ACTIVE language — never a
        fixed f-string (V2 fix 2026-07-23: `voice.proactive.notify`/`_deliver` speak exactly what they receive,
        without passing through an LLM turn that could re-localize it)."""
        return getattr(self._lang(), template).format(**kw)

    def _budget_for(self, kind: str) -> float:
        """Wall-clock budget by kind (WORKER_BUDGET_<KIND>_SECS takes precedence; then global; 0 = unlimited)."""
        try:
            v = os.getenv(f"WORKER_BUDGET_{(kind or '').upper()}_SECS")
            if v:
                return float(v)
        except Exception:
            pass
        return self._kind_budget_default.get(kind or "", self._budget_secs)
