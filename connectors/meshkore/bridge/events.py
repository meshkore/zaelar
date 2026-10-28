"""Inbound side of the cluster bridge: every peer frame lands in `on_event` (see `__init__.py`)."""
import json

from connectors.meshkore import store, journal, security, mem_ingest, capsule


class _EventsMixin:
    def _catch_up_context(self, cluster: str, peer: str) -> str | None:
        """Was `peer`'s last MESSAGE to us ever answered? None if answered/never messaged/already nudged for
        this exact message. Operator report (2026-07-25): 'I start this up 3 days later and there are messages
        we never replied to' — a MeshKore cluster has NO server-side unread count (client.py: no message
        history, relay-only), so catching up is OUR job, reconstructed from the durable journal (survives a
        restart, unlike the /debug timeline). Deduped by exact message timestamp so a flaky reconnect loop
        doesn't re-nudge for the SAME still-unanswered message every time; a genuinely NEW message gets a fresh
        nudge (different timestamp)."""
        try:
            ex = journal.last_exchange(cluster, peer)
        except Exception:
            return None
        ts = ex.get("last_in_ts")
        if not ts:
            return None
        out_ts = ex.get("last_out_ts")
        if out_ts is not None and out_ts >= ts:
            return None                                    # already answered (or later)
        key = (cluster, peer, ts)
        if key in self._caught_up:
            return None
        self._caught_up.add(key)
        return ex.get("last_in_text") or ""

    # ── inbound: manager sink ──────────────────────────────────────────────────────────────────────────────
    async def on_event(self, ev: dict):
        """Every frame from every cluster lands here (see MeshKoreClient._emit)."""
        journal.record({"chan": "in", **ev})                     # full post-mortem trail (redacted)
        # MeshKore tags frames with "kind" (message/ready/presence/ack/error); keep "type" as a fallback.
        t = ev.get("kind") or ev.get("type")
        cluster = ev.get("cluster", "?")
        if t == "message":
            self._on_message(ev, cluster)
        elif t == "presence":
            ag, st = ev.get("agent"), ev.get("status")
            _b._emit("cluster", f"• {cluster}: {ag} {st}", extra={"cluster": cluster, "peer": ag, "status": st})
            # V2-067 (operator request, 2026-07-24): NO predefined data/objective on connect — the widget only
            # facilitates the connection; the operator decides what to discuss, with their own instructions. The
            # ONLY automatic thing allowed is a brief intro (name+capabilities), and ONLY the first time we meet this
            # peer (durable memory via mem_ingest.known_peer — reconnecting to someone already known and introducing
            # ourselves again would be absurd). If there is a real active task (`self._engaged`), that comes from an
            # explicit operator instruction, not this presence event.
            if st == "online" and not mem_ingest.known_peer(cluster, ag):
                self._nudged.discard(cluster)
                ag_s = security.neutralize_identity(ag)             # peer-chosen handle → neutralize before the prompt (V2)
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · event] agent '{ag_s}' just came online and you've never talked before. "
                    f"Send a SHORT self-introduction — your name and a one-line generic description of your "
                    f"capabilities. Do NOT propose an objective or a specific task (that's the operator's call). "
                    f"You MAY briefly propose WORKING NORMS for how you two communicate and, if it agrees, record "
                    f"them with [[cluster.pact:{cluster}]]{{\"to\":\"{ag_s}\",...}}[[/cluster.pact]]. {capsule.PACT_DEFAULT_PROPOSAL}"))
                capsule.patch(cluster, ag, greeted=True)   # V2-069: presentado → no repetirlo (fase avanza a sondeo)
            elif st == "online":
                # known -> no intro, but may have an unanswered message from when we were offline (operator request
                # 2026-07-25: "there are messages they sent us that we have not answered").
                pending = self._catch_up_context(cluster, ag)
                if pending is not None:
                    self._last_activity[cluster] = self._now()
                    self._nudged.discard(cluster)
                    ag_s = security.neutralize_identity(ag)
                    self._spawn(self._brain_turn(
                        cluster,
                        f"[cluster:{cluster} · event] agent '{ag_s}' is back online. Their LAST message to you was "
                        f"never answered (you were offline): {security.fence_untrusted(pending)}\nDecide: reply now "
                        f"if it still needs one, or note it's stale/no longer relevant — your call.",
                        peer=ag, peer_text=pending))
            self._notify_registry()
        elif t == "ready":
            online = ev.get("online") or []
            _b._emit("cluster", f"✓ joined {cluster}", extra={"cluster": cluster, "online": online})
                # V2-067: same criterion as above — only introduce ourselves to peers NEVER seen in this cluster,
                # never open a "collaboration" or propose an objective on our own. If EVERYONE present is already
                # known, stay silent (avoids an absurd "hello again" on every reconnection).
            unknown = [p for p in online if not mem_ingest.known_peer(cluster, p)]
            if unknown:
                self._last_activity[cluster] = self._now()
                self._nudged.discard(cluster)
                unknown_s = ", ".join(security.neutralize_identity(h) for h in unknown)   # peer handles → neutralize (V2)
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · event] you just connected; agent(s) online you've never talked to before: "
                    f"{unknown_s}. Send a SHORT self-introduction — your name and a one-line generic "
                    f"description of your capabilities. Do NOT propose an objective or a specific task (that's the "
                    f"operator's call). You MAY briefly propose WORKING NORMS for how you communicate and, if they "
                    f"agree, record them with [[cluster.pact:{cluster}]]{{\"to\":\"<agent>\",...}}[[/cluster.pact]]. "
                    f"{capsule.PACT_DEFAULT_PROPOSAL}"))
                for _p in unknown:
                    capsule.patch(cluster, _p, greeted=True)   # V2-069: presentado → fase avanza, no re-presentarse
                # CATCH-UP (operator request 2026-07-25): an ALREADY KNOWN peer may have written while we were
                # disconnected (sometimes for days) — MeshKore has no server history (client.py: relay to whoever is
                # connected NOW), so if no one picks those messages up on reconnect, they are silently lost forever.
                # One per known peer, each with its own context/trace.
            for p in (peer for peer in online if peer not in unknown):
                pending = self._catch_up_context(cluster, p)
                if pending is None:
                    continue
                self._last_activity[cluster] = self._now()
                self._nudged.discard(cluster)
                p_s = security.neutralize_identity(p)
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · event] you just (re)connected. Agent '{p_s}' messaged you while you "
                    f"were offline and it was never answered: {security.fence_untrusted(pending)}\nDecide: reply "
                    f"now if it still needs one, or note it's stale/no longer relevant — your call.",
                    peer=p, peer_text=pending))
            self._notify_registry()
        elif t == "status":
            # the WHY travels with it (demo pass 30: «meshcore: error» with an empty text — the client knew the
            # reason and the detail, the event dropped them)
            _why = " · ".join(str(x) for x in (ev.get("reason"), ev.get("detail")) if x)
            _b._emit("cluster", f"{cluster}: {ev.get('status')}", text=_why[:200],
                  extra={"cluster": cluster, "status": ev.get("status"), "reason": ev.get("reason") or "",
                         "detail": str(ev.get("detail") or "")[:200]})
            self._notify_registry()
        elif t == "ack":
            if ev.get("delivered") == 0:
                _b._emit("cluster", f"⚠ {cluster}: recipient offline", extra={"cluster": cluster})
                self._notify_registry()
        elif t == "error":
            _b._emit("error", f"cluster {cluster}: {store.redact(json.dumps(ev, ensure_ascii=False))}")
            self._notify_registry()

    def _on_message(self, ev: dict, cluster: str):
        """A peer MESSAGE frame: echo filter, anti-spam dedup + stall guard, metering, then one brain turn."""
        frm = ev.get("from") or "?"
        client = self._manager.get(cluster)
        if client and frm == client.handle:
            return                                            # ignore our own echoes
        # NEUTRALIZED handle as the UNIQUE peer key (V2-069): the peer chooses the handle and it may vary
        # (added garbage/fence-forge). Dedup, stall guard, and capsule must index by the SAME sanitized handle
        # — otherwise a variable handle would fragment the key, evade dedup/stall detection, and split the
        # relationship memory across multiple capsules. `neutralize_identity` collapses those variants to the
        # same peer.
        peer_h = security.neutralize_identity(frm)
        # Canonical §4 content: payload is a STRING → it's text; an OBJECT → read .text and .media[{mime,url|b64}].
        # No "type"/threading fields exist (presence/joins come as their OWN frames, not as message payloads).
        payload = ev.get("payload")
        media = None
        if isinstance(payload, str):
            text = payload
        elif isinstance(payload, dict):
            text = payload.get("text") or ""
            media = payload.get("media") or None
            if not text and not media:
                text = json.dumps(payload, ensure_ascii=False)   # unknown structured shape → give the brain the raw
        else:
            text = str(payload) if payload is not None else ""
        self._last_activity[cluster] = self._now()
        self._nudged.discard(cluster)
        self._last_peer_msg[cluster] = text     # idle-nudge context (found bug 2026-07-25: see _heartbeat)
        # ANTI-SPAM DEDUP (2026-07-25): a peer re-sending the SAME status text within DEDUP_SECS is a loop/spam
        # (zalo did this 45× live) — record it for observability but do NOT spawn another brain turn (no token
        # burn, no inflight-queue flood, no 40× "quedo a la espera"). Compared on a NORMALIZED key (casefold +
        # only alnum+spaces, emojis/punctuation/encoding stripped) because zalo alternated two spellings of the
        # SAME ping ("...un momento" vs "…🧠 un momento") to slip past an exact match. Empty/attachment bypass.
        _dk = (cluster, peer_h)
        _prev = self._recent_inbound.get(_dk)
        _txt = (text or "").strip()
        _key = _b._dedup_key(_txt)
        if _key and _prev and _prev[0] == _key and (self._now() - _prev[1]) < _b.DEDUP_SECS:
            self._recent_inbound[_dk] = (_key, self._now())   # slide the window; keep suppressing a sustained loop
            # STALL GUARD (V2-069): a repeat is not just "ignore" — it is a loop signal. We count repetitions
            # and act like a human: at 2 we send ONE assertive message anchored to the objective (once only);
            # if it continues, we go SILENT and alert the operator ONCE. This replaces the "just ignore it"
            # behavior that let zalo repeat "one moment" 1,333 times without anyone breaking the pattern.
            self._repeat[_dk] = self._repeat.get(_dk, 0) + 1
            st = self._stall.setdefault(_dk, {"assertive_sent": False, "alerted": False})
            verdict = capsule.stall_verdict(self._repeat[_dk], 0)
            frm_s0 = peer_h
            if verdict == "asertivo" and not st["assertive_sent"]:
                st["assertive_sent"] = True
                _b._emit("cluster", f"⇠ {cluster}·{frm_s0} (bucle → mensaje asertivo)",
                      extra={"cluster": cluster, "peer": frm_s0, "dir": "in", "stall": "assertive"})
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · message from agent '{frm_s0}']\n{security.fence_untrusted(_txt)}\n"
                    f"[SITUACIÓN] Este agente repite lo mismo y no avanzáis. Manda UN mensaje directo y breve, "
                    f"anclado al objetivo: señala que seguís igual y pide el siguiente paso CONCRETO; si no hay "
                    f"avance, di con cortesía que lo dejáis aquí. Nada de más cortesías ni de presentarte.",
                    peer=frm_s0, peer_text=_txt))
            elif verdict == "callar":
                if not st["alerted"]:
                    st["alerted"] = True
                    _b._emit("error", f"cluster {cluster}: «{frm_s0}» lleva {self._repeat[_dk]} repeticiones sin "
                          f"avanzar — dejo de responder (bucle). Revisa si merece la pena seguir con este agente.")
                _b._emit("cluster", f"⇠ {cluster}·{frm_s0} (bucle, en silencio)",
                      extra={"cluster": cluster, "peer": frm_s0, "dir": "in", "stall": "silent"})
            else:
                _b._emit("cluster", f"⇠ {cluster}·{frm_s0} (repetido, ignorado)",
                      extra={"cluster": cluster, "peer": frm_s0, "dir": "in", "dedup": True})
            self._notify_registry()
            return
        if _key:
            self._recent_inbound[_dk] = (_key, self._now())
            # NEW content -> close any loop episode that existed: reset counters/state.
            self._repeat[_dk] = 0
            self._stall.pop(_dk, None)
        # SSE/timeline/observer copy is REDACTED: a peer message can carry a secret-shaped value (or echo back
        # one of our own tokens) and this surface persists to logs + streams to the UI (audit V6). The brain
        # copy below stays raw (fenced) — Hermes needs the real content to collaborate; the fence handles trust.
        frm_lbl = peer_h                                   # V2-069: unique peer key (neutralized above)
        _b._emit("cluster", f"⇠ {cluster}·{frm_lbl}", text=store.redact(text), role="peer",
              extra={"cluster": cluster, "peer": frm_lbl, "dir": "in", "media": media})
        note = text + (f"\n[{len(media)} attachment(s): " + ", ".join(
            (m.get("mime") or "file") + (" " + m["url"] if m.get("url") else "") for m in media) + "]" if media else "")
        # The peer's content is UNTRUSTED — fence it so the brain reads it as data, not instructions (the
        # header before it is our own trusted label). Our security rules get reasserted at the END in _brain_turn.
        # The handle itself is ALSO peer-chosen: neutralized above (peer_h) so a crafted handle can't forge a
        # fence-close + fake trailer in the trusted header (audit V2).
        # RESOURCE BALANCE (V2-071): measure what the peer CONTRIBUTES and whether it asks us to PRODUCE work
        # (offload). This is a per-peer signal accumulated by the capsule; the verdict is calculated in
        # _brain_turn before generation.
        try:
            capsule.meter(cluster, frm_lbl, received=len(text or ""),
                          offload=security.looks_like_offload(text or ""))
        except Exception:
            pass
        # Conversation WINDOW (V2-075): record the peer message so the model-based EVALUATOR (heartbeat,
        # off-hot-path) can judge the chat health INTELLIGENTLY — NOT with hardcoded patterns. If the evaluator
        # already decided to PAUSE with this peer, we do not bombard again: only real progress re-engages, which
        # the evaluator itself will recognize on its next pass (we do not judge by regex here).
        self._window_add(cluster, frm_lbl, "peer", _txt)
        if self._paced.get(_dk, {}).get("paused"):
            _b._emit("cluster", f"⇠ {cluster}·{frm_lbl} (en pausa por el evaluador, a la espera)",
                  extra={"cluster": cluster, "peer": frm_lbl, "dir": "in", "pace": "paused"})
            self._notify_registry()
            return
        self._spawn(self._brain_turn(
            cluster, f"[cluster:{cluster} · message from agent '{frm_lbl}']\n{security.fence_untrusted(note)}",
            peer=frm_lbl, peer_text=text))
        self._notify_registry()


# Shared state is read through the facade module object, so a patch of `connectors.meshkore.bridge.<name>` is seen here.
from connectors.meshkore import bridge as _b  # noqa: E402
