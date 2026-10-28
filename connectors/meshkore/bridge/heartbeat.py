"""What the heartbeat decides to do on its own: the idle nudge and the conversation evaluator (see `__init__.py`)."""
from loguru import logger

from connectors.meshkore import security, mem_ingest, capsule


class _HeartbeatMixin:
    def _heartbeat_context(self, cluster: str) -> str:
        """Best-effort 'what was the peer last saying' for the idle nudge below, so the brain isn't asked to
        decide blind. Prefers the live in-process text from THIS run; falls back to the durable per-peer synthesis
        (`mem_ingest`, survives a restart) — same untrusted-peer content the brain already sees on every
        message turn, no new trust surface. Empty if genuinely nothing is known yet."""
        last = self._last_peer_msg.get(cluster)
        if last:
            return last
        client = self._manager.get(cluster)
        for p in (client.online if client else []) or []:
            s = mem_ingest.synthesis_for(cluster, p)
            if s:
                return s
        return ""

    async def _heartbeat_nudge(self, cluster: str):
        """Run the idle-nudge brain turn, then decide what 'nudged' should mean.

        BUG (found live 2026-07-25, journal .meshkore/logs/meshkore.jsonl): the ORIGINAL heartbeat prompt carried
        ZERO context — the brain was asked to "decide: follow up, or conclude" with no idea what the peer last
        said, so a peer's "one moment, checking with my team" got answered with [[cluster.done]] (conversation
        closed while the peer was still actively working). Fixed by feeding it the last known message/topic.

        That fix uncovered a SECOND bug: `_nudged` used to be marked permanently on every heartbeat firing,
        regardless of outcome — so once the brain (correctly) chose to stay silent and wait, the cluster went
        quiet FOREVER (only a fresh inbound message clears `_nudged`). A single "still waiting" turn must not
        permanently mute us if the peer never comes back. Only a REAL cluster.send or cluster.done should count
        as "we already nudged" — silence re-arms the idle timer so we check again after another IDLE_SECS.
        """
        ctx = self._heartbeat_context(cluster)
        ctx_block = f"\nThe peer's last known message/topic: {security.fence_untrusted(ctx)}" if ctx else ""
        event_text = (
            f"[cluster:{cluster} · heartbeat] no reply for a while and peers are online.{ctx_block}\n"
            f"If that shows the peer is still actively working (e.g. \"one moment\", \"checking with my team\", "
            f"\"give me a second\"), do NOT conclude — stay silent (no tags at all) and keep waiting. Only send a "
            f"gentle follow-up if genuinely stuck with no signal either way, or emit [[cluster.done:{cluster}]] "
            f"if the objective is truly finished.")
        _, sent = await self._brain_turn(cluster, event_text, origin="pulso")
        if not sent and self._engaged.get(cluster):
            self._last_activity[cluster] = self._now()   # re-arm: check again after another idle stretch
            self._nudged.discard(cluster)

    # ── INTELLIGENCE-based conversation criterion (V2-075) — the model judges health, code applies it ───────────
    def _window_add(self, cluster: str, peer: str, who: str, text: str):
        """Record a turn (peer/us) in the relationship window for the evaluator to read. Bounded."""
        if not (text or "").strip() or not peer:
            return
        dk = (cluster, peer)
        w = self._window.get(dk, [])
        w.append({"who": who, "text": text})
        self._window[dk] = w[-14:]

    async def _evaluate_and_apply(self, cluster: str, peer: str):
        """Run the conversation through the EVALUATOR (generic model) and apply its closed-catalog verdict. Off-turn;
        fail-open. The DECISION belongs to the model; this only executes it (hand back / pause / concise)."""
        dk = (cluster, peer)
        win = self._window.get(dk, [])
        if len(win) < 4:                       # too little conversation for a well-grounded judgment
            return
        self._last_eval[dk] = self._now()
        try:
            from connectors.meshkore import evaluator, brain
            cap = capsule.load(cluster, peer)
            metrics = {"turns": cap.get("turns", 0), "given": cap.get("given", 0),
                       "received": cap.get("received", 0),
                       "ratio": cap.get("given", 0) / max(cap.get("received", 1), 1)}
            verdict = await evaluator.evaluate(win, metrics, spec=brain._spec())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cluster evaluator failed (fail-open): {e}")
            return
        action = verdict.get("action", "continue")
        _b._emit("cluster", f"⚖ {cluster}·{peer}: evaluador → {verdict.get('health')}/{action}",
              extra={"cluster": cluster, "peer": peer, "dir": "eval", "eval": verdict})
        ps = self._paced.setdefault(dk, {"paused": False, "alerted": False, "concise": False})
        if action == "continue":
            self._paced.pop(dk, None)          # healthy -> clear any previous pause/concise state
            return
        if action == "concise":
            ps["concise"] = True               # the next turn will be concise (injected in _brain_turn)
            return
        if action in ("hand_back", "pause"):
            if action == "pause":
                ps["paused"] = True            # stop replying until the evaluator sees real progress
                if not ps["alerted"]:
                    ps["alerted"] = True
                    # T-03 (2026-07-26 audit remediation): GENERAL objective-ownership guard — previously
                    # `off_track` alerted with the SAME generic message as `dead_end` ("no progress"), without
                    # distinguishing "the other side is not following" from "the other side is taking me somewhere
                    # ELSE". A peer trying to redirect the collaboration is exactly the case the operator wants
                    # NOTIFIED and permission-requested (not decided by the system alone, nor silently) — distinct
                    # from the narrow V2-076 guard (which only protects the dev-worker); this covers conversation in
                    # general.
                    if verdict.get("health") == "off_track":
                        _obj = (cap.get("objective") or "").strip()
                        _obj_txt = f"tu objetivo fijado con «{peer}» es «{_obj}»" if _obj else \
                            f"no tenías ningún objetivo fijado con «{peer}»"
                        _b._emit("error", f"cluster {cluster}: «{peer}» parece querer llevar la charla hacia OTRA "
                              f"cosa ({_obj_txt}) — {verdict.get('reason') or 'sin motivo dado'}. Me paro y "
                              f"espero tu decisión: ¿seguimos por ahí, fijo el objetivo con set_cluster_objective, "
                              f"o le digo que no?")
                    else:
                        _b._emit("error", f"cluster {cluster}: paro con «{peer}» — {verdict.get('reason') or 'sin avance'}. "
                              f"Me quedo a la espera; revisa si merece seguir con este agente.")
            # hand the turn back ONCE with one sentence (the mind writes it), then stay silent. origin="pulso":
            # the EVALUATOR ran off the heartbeat tick (throttled by EVAL_SECS), not off a fresh peer message —
            # same reasoning as _heartbeat_nudge below.
            self._spawn(self._brain_turn(
                cluster, f"[cluster:{cluster} · evaluación de la conversación]\n{capsule.PACE_HANDBACK}", peer=peer,
                origin="pulso"))


# Shared state is read through the facade module object, so a patch of `connectors.meshkore.bridge.<name>` is seen here.
from connectors.meshkore import bridge as _b  # noqa: E402
