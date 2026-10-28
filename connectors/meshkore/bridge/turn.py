"""The brain turn of the cluster bridge and the routing of its reply (see `__init__.py`)."""
import time

from loguru import logger

from voice.tag_protocol import strip_tags
from connectors.meshkore import brief, store, journal, security, mem_ingest, capsule


class _TurnMixin:
    # ── the brain turn (off the voice pipeline) ──────────────────────────────────────────────────────────────
    async def _brain_turn(self, cluster: str, event_text: str, peer: str | None = None,
                          peer_text: str | None = None, origin: str = "cluster"):
        # TRACEABILITY (V2-044): a peer message is also a stimulus -> it starts with its trace. `origin` defaults
        # to "cluster" (a REAL inbound peer message/reconnect) but `_heartbeat_nudge` passes "pulso" — WE decided
        # to check in, nothing came in from the peer, and that distinction is what lets a flow viewer
        # tell a real task apart from housekeeping instead of dimming/conflating
        # a genuine cluster conversation with our own idle nudging (2026-08-16 operator finding: a heartbeat nudge
        # was opening a visible "en curso" flow after minutes of total silence — the pulse must not manufacture
        # tasks just because it has a loop running; see CLAUDE.md's "a task/flow only ever opens from one of
        # four sources" invariant).
        # _brain_turn runs as its own task (create_task) -> the ctxvar is scoped to this turn.
        trace_id = ""
        try:
            from voice import trace as _trace
            trace_id = _trace.begin((peer_text or event_text or "")[:200], origin=origin)
        except Exception:
            pass
        # CAPSULE (V2-069 "one mind"): the mind SITUATES itself in the relationship before replying — who the peer
        # is, what you have discussed, the objective, what has already been decided, and the PHASE (which tells it,
        # e.g., NOT to re-introduce itself during work/probing). This is OUR relationship memory (distilled dossier)
        # — not raw peer text. Without a specific peer (heartbeat/global ready), it is omitted. It goes BEFORE the
        # event and BEFORE the trailer (our security prompt still goes last).
        rel_block = ""
        res_verdict = "equilibrado"
        if peer:
            try:
                cap = capsule.load(cluster, peer)
                cap["phase"] = capsule.derive_phase(cap)
                rel_block = capsule.compose(cluster, peer, cap) + "\n\n"
                # RESOURCE BALANCE (V2-071): is the peer offloading expensive work to us? If the balance is biased
                # or in exploitation, inject a SILENT directive (be brief · code through the repo, not through the
                # channel) — this is not communicated to the peer; we simply steer differently. It goes inside the
                # relationship block (before the security trailer, which still goes last).
                res_verdict = capsule.resource_verdict(
                    int(cap.get("given") or 0), int(cap.get("received") or 0),
                    int(cap.get("offloads") or 0), int(cap.get("turns") or 0))
                guide = capsule.resource_guidance(res_verdict)
                if guide:
                    rel_block += guide + "\n\n"
                # CONVERSATION PACT (V2-072, 3rd rule level): the norms NEGOTIATED with this agent
                # (cadence/medium/scope) — the mind must respect them. They sit below the security trailer
                # (level 1) and the operator rules (level 2), which a pact cannot loosen.
                pact_block = capsule.pact_compose(cap)
                if pact_block:
                    rel_block += pact_block + "\n\n"
                # V2-075: if the EVALUATOR (model) judged the chat imbalanced, this turn goes CONCISE (once).
                if self._paced.get((cluster, peer), {}).get("concise"):
                    rel_block += ("[RITMO] Sé BREVE y concreto: no añadas detalle de más; el otro va más despacio o "
                                  "producís vosotros mucho más.\n\n")
                    self._paced[(cluster, peer)]["concise"] = False
            except Exception:
                rel_block = ""
        # Security rule of thumb: OUR prompt goes LAST. The trailer (do-not-reveal + injection defense) is appended
        # after the (possibly hostile) event content so a peer's "ignore all previous rules" can never sit after it.
        trailer = security.trailer()
        framed = f"{brief.for_brain()}\n\n{rel_block}{event_text}" + (f"\n\n{trailer}" if trailer else "")
        # Cluster PERMISSIONS (V2-076): default NONE -> no tools -> turn behaves as usual (pure untrusted). If the
        # operator granted capabilities to THIS cluster (on connect), the turn offers the FlashBrain catalog subset
        # and escalates BOUNDED. Only on a real PEER turn (not greetings/nudges without a peer).
        _tool_names = None
        _escalate_ctx = None
        if peer:
            try:
                from connectors.meshkore import perms as _perms
                _p = store.get_perms(cluster)
                if _perms.any_capability(_p):
                    _tool_names = _perms.gated_tool_names(_p)
                    _escalate_ctx = _perms.escalate_context(cluster, _p)
                    # OBJECTIVE OWNERSHIP guard (2026-07-26 audit, P0 finding — previously ZERO code despite being
                    # documented as a pending invariant): the 'code' permission granted to the cluster is NOT enough
                    # by itself to trigger a dev-worker — the OPERATOR must have set the OBJECTIVE of THIS
                    # collaboration (capsule.objective, never written by the peer).
                    _gated = _perms.gate_dev_by_objective(_escalate_ctx, cap.get("objective"))
                    if _gated is not _escalate_ctx:
                        _escalate_ctx = _gated
                        if not cap.get("_objective_gate_notified"):
                            cap["_objective_gate_notified"] = True
                            capsule.save(cluster, peer, cap)
                            _b._emit("resource", "🔒 permiso 'code' concedido pero SIN objetivo del operador — "
                                              "dev-worker bloqueado hasta que se fije uno",
                                  extra={"cluster": cluster, "peer": peer})
            except Exception:
                _tool_names = None
        t0 = time.time()
        try:
            reply = await self._brain(framed, tool_names=_tool_names, escalate_ctx=_escalate_ctx)
        except Exception as e:
            logger.warning(f"MeshKore brain turn failed: {e}")
            _b._emit("error", f"cluster brain turn failed: {e}")
            _b._close_cluster_flow(trace_id)
            return "", []
        cluster_ms = round((time.time() - t0) * 1000)
        spoken, sent = await self._route_reply(reply)
        self._after_reply(cluster, peer, peer_text, spoken, sent, res_verdict)
        if spoken.strip():
            # INVARIANT: the cluster channel NEVER reaches the speaker. Anything the brain says here is agent-to-agent
            # or an aside for the /debug wall — it goes to the UI observer ONLY, never to TTS. The operator hears
            # cluster activity only if the brain deliberately turns it into a voice reply (a normal user turn) or a
            # proactive.notify — both of which pass through the voice/speech.py gate. Do NOT add a speak() call here.
            # redact in case the brain echoed a token/secret back into its operator-facing aside.
            _b._emit("cluster", "🧠 zaelar", text=store.redact(spoken.strip()), role="assistant",
                  extra={"cluster": cluster, "dir": "note", "cluster_ms": cluster_ms})
        _b._close_cluster_flow(trace_id)
        return spoken, sent

    def _after_reply(self, cluster: str, peer: str | None, peer_text: str | None, spoken: str,
                     sent: list, res_verdict: str) -> None:
        """After the reply of a MESSAGE turn: passive memory observation, capsule bookkeeping, resource balance."""
        # PASSIVE cluster-to-memory OBSERVATION (V2-021 T170): only on a MESSAGE turn from a peer (not presence/
        # heartbeat). Distills inbound+outbound into a QUARANTINED synthesis per peer, off-hot-path and
        # fire-and-forget — the channel has no tools; this grants it no capabilities. `sent` = what actually went to
        # the peer (already passed through the outbound guard); if nothing was sent, fall back to the `spoken` aside.
        if peer_text is not None and peer:
            mem_ingest.observe_exchange(cluster, peer, peer_text, "\n".join(sent) or spoken)
            # CAPSULE (V2-069): we have now exchanged with this peer -> mark greeted (do not re-introduce),
            # increment a substantive turn, and re-derive the phase. Cheap and direct (sys_kv). Does not touch the
            # operator state.
            try:
                cap = capsule.load(cluster, peer)
                cap["greeted"] = True
                cap["turns"] = int(cap.get("turns") or 0) + 1
                cap["phase"] = capsule.derive_phase(cap)
                capsule.save(cluster, peer, cap)
            except Exception:
                pass
            # RESOURCE BALANCE (V2-071): measure what WE have produced for this peer (our spend) + whether we sent
            # code. If the balance is in EXPLOITATION, alert the operator ONCE (silent toward the peer) — this is the
            # detection the operator requested ("so we can detect that").
            try:
                out_text = "\n".join(sent) or spoken or ""
                capsule.meter(cluster, peer, given=len(out_text),
                              code_out=("```" in out_text or "def " in out_text))
                self._window_add(cluster, peer, "us", out_text)   # V2-075: our turn enters the evaluator window
                if res_verdict != "equilibrado":
                    _b._emit("resource", f"⚖ {cluster}·{peer}: balance {res_verdict}",
                          extra={"cluster": cluster, "peer": peer, "balance": res_verdict})
                if res_verdict == "explotación":
                    _dk = (cluster, peer)
                    if _dk not in self._resource_alerted:
                        self._resource_alerted.add(_dk)
                        _b._emit("error", f"cluster {cluster}: «{peer}» está descargando trabajo en ti (gasta tus "
                              f"recursos generando código/trabajo sin reciprocidad). He empezado a acortar y a "
                              f"remitir al repositorio. Revisa si esta colaboración te compensa.")
                elif res_verdict == "equilibrado":
                    self._resource_alerted.discard((cluster, peer))   # re-arm the alert if the pattern returns
            except Exception:
                pass

    # A reply generated FROM a cluster turn is untrusted output: a peer could have prompt-injected the brain into
    # emitting a tag. So from this path we allow ONLY the collaboration primitives (talk to peers / conclude).
    # cluster.connect (join an attacker cluster, persisted) and cluster.disconnect (sever a real collaboration) are
    # operator-only — reachable from the voice path and REST, never from an inbound peer message. Least privilege.
    _CLUSTER_TURN_ALLOWED = {"cluster.send", "cluster.done", "cluster.pact"}

    async def _route_reply(self, reply: str) -> tuple[str, list[str]]:
        """Strip [[cluster.*]] tags out of the reply, dispatch the ALLOWED ones, and return (remaining_text,
        sent_texts) — `sent_texts` = the messages actually delivered to the cluster (post outbound-guard), used by
        the passive memory observation to record what zaelar said to the peer."""
        actions: list = []

        def collect(action, extra):
            if action in self._CLUSTER_TURN_ALLOWED:
                actions.append((action, extra))
            elif action.startswith("cluster."):
                # blocked over-privileged tag from an untrusted turn — drop it and alert the operator.
                journal.record({"chan": "out", "action": action, "blocked": "not allowed from a cluster turn"})
                _b._emit("error", f"cluster: blocked '{action}' emitted during a cluster turn (operator-only action).")
            # widget/cron/show/close tags emitted off-pipeline have no canvas/context here — drop silently.

        spoken, _ = strip_tags(reply or "", collect, final=True)
        sent: list[str] = []
        for action, extra in actions:
            out = await self.dispatch(action, extra)
            if out:
                sent.append(out)
        return spoken, sent


# Shared state is read through the facade module object, so a patch of `connectors.meshkore.bridge.<name>` is seen here.
from connectors.meshkore import bridge as _b  # noqa: E402
