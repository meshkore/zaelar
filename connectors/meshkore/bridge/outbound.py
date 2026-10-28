"""Outbound side of the cluster bridge: a [[cluster.*]] tag becomes an action on the manager (see `__init__.py`)."""
import asyncio

from loguru import logger

from connectors.meshkore import store, journal, security, capsule, send_gate


class _OutboundMixin:
    def _resolve_peer_cluster(self, handle: str) -> str | None:
        """Resolve a (possibly brain-confused) peer handle to the correct cluster name. Returns the cluster name
        whose 'online' set includes *handle*, or the only connected cluster as fallback, or None."""
        for c in self._manager.clusters():
            if handle in c.get("online", []):
                return c["name"]
        # Only one cluster connected → it's a safe default (the brain named the peer, not the cluster).
        names = self._manager.names()
        if len(names) == 1:
            return names[0]
        return None

    # ── outbound: execute a [[cluster.*]] tag (also called from the voice path) ─────────────────────────────
    async def dispatch(self, action: str, extra: dict) -> str | None:
        """Execute a [[cluster.*]] tag. Returns the text actually SENT to the peer for a successful cluster.send
        (post outbound-guard), else None — the caller uses it to record the exchange in the passive memory."""
        journal.record({"chan": "out", "action": action, "extra": extra})
        try:
            if action == "cluster.connect":
                data = extra.get("data") or {}
                name = (data.get("name") or "").strip()
                if not name:
                    _b._emit("error", "cluster.connect: missing 'name'")
                    return
                creds = store.resolve(name, data.get("cluster_id", ""), data.get("token", ""),
                                      data.get("handle", ""), data.get("vis", ""))
                if not creds:
                    # V2-086: the message distinguishes both modes — a PUBLIC cluster only needs the id, so
                    # "missing credentials" would be false and would send the operator looking for a nonexistent token.
                    _b._emit("error", f"cluster.connect '{name}': falta el cluster_id "
                                   "(y el token, si el cluster es privado)")
                    return
                _vis = creds.get("vis", "")
                # Alias COLLISION guard (V2-086): never overwrite another cluster's credentials because the model
                # reused a default name. See store.unique_name.
                _orig = name
                name = store.unique_name(name, creds["cluster_id"])
                if name != _orig:
                    _b._emit("cluster", f"alias «{_orig}» ya es de otro cluster → se usa «{name}»",
                          extra={"cluster": name})
                await self._manager.connect(name, creds["cluster_id"], creds["token"], creds.get("handle"),
                                            vis=_vis)
                store.save_cluster(name, creds["cluster_id"], creds["token"], creds.get("handle", "zaelar"),
                                   vis=_vis)
                # Connect-time PERMISSIONS (V2-076): the operator may grant capabilities to THIS cluster in the same
                # act of connecting (e.g. code+repo). By default (without `perms`) the cluster stays at maximum security.
                if isinstance(data.get("perms"), dict):
                    store.set_perms(name, data["perms"])
                    _b._emit("cluster", f"🔐 {name}: permisos fijados por el operador",
                          extra={"cluster": name, "perms": store.get_perms(name)})
                # Connecting = there's an active objective on this cluster. Marking it engaged NOW means a peer
                # arriving later (presence:online) wakes the brain to open the collaboration, even if we joined an
                # empty channel and haven't sent anything yet. Cleared by [[cluster.done]]/[[cluster.disconnect]].
                self._engaged[name] = True
                self._last_activity[name] = self._now()
                _b._emit("cluster", f"→ connecting {name}", extra={"cluster": name})
            elif action == "cluster.send":
                return await self._send(extra)
            elif action == "cluster.pact":
                # CONVERSATION PACT (V2-072): the mind records AGREED norms with the peer (cadence/medium/scope).
                # It is sanitized to the closed vocabulary and stored in the per-peer capsule (by="peer" -> an
                # operator pact would still outrank it). It never grants capabilities; it only restricts our behavior.
                # Nothing goes out to the channel (the prose agreement was already said by the mind in cluster.send).
                data = extra.get("data") or {}
                if not self._manager.has(name):
                    resolved = self._resolve_peer_cluster(name)
                    name = resolved or name
                to = data.get("to")
                peer_h = security.neutralize_identity(to) if to else None
                if peer_h:
                    capsule.pact_set(name, peer_h, data, by="peer")
                    _b._emit("cluster", f"🤝 {name}·{peer_h}: pacto actualizado",
                          extra={"cluster": name, "peer": peer_h, "pact": capsule.load(name, peer_h).get("pact")})
                else:
                    _b._emit("error", "cluster.pact: falta 'to' (con qué agente se pacta) — ignorado.")
                return
            elif action == "cluster.done":
                name = extra.get("name") or ""
                if not self._manager.has(name):
                    resolved = self._resolve_peer_cluster(name)
                    if resolved:
                        name = resolved
                if self._manager.has(name):
                    self._engaged[name] = False
                    # V2-069: the conversation with this cluster's peers CONCLUDED -> mark their capsule as CLOSURE
                    # phase (faithful state; mem_ingest already maintains the durable dossier, the capsule is compact
                    # with no firehose). This is not final: a new message re-derives the phase and re-engages. Reset
                    # the stall counter so the episode is not carried into a future resumption.
                    client = self._manager.get(name)
                    for _p in (client.online if client else []) or []:
                        _ph = security.neutralize_identity(_p)
                        capsule.patch(name, _ph, phase=capsule.CIERRE)
                        self._repeat.pop((name, _ph), None)
                        self._stall.pop((name, _ph), None)
                    _b._emit("cluster", f"✔ {name}: task concluded", extra={"cluster": name})
                    self._notify_registry()
            elif action == "cluster.disconnect":
                name = extra.get("name") or ""
                if not self._manager.has(name):
                    resolved = self._resolve_peer_cluster(name)
                    if resolved:
                        name = resolved
                self._engaged.pop(name, None)
                await self._manager.disconnect(name)
        except Exception as e:
            logger.warning(f"MeshKore dispatch {action} failed: {e}")
            _b._emit("error", f"cluster {action} failed: {e}")

    async def _send(self, extra: dict) -> str | None:
        """`cluster.send`: resolve the cluster, salvage a malformed body, scan outbound, pace, deliver."""
        name = extra.get("name") or ""
        data = extra.get("data") or {}
        to, text = data.get("to"), data.get("text", "")
        # RESILIENT NAME RESOLUTION: the brain sometimes emits [[cluster.send:<peer_handle>]]; if no cluster
        # matches `name`, resolve it as a peer handle across all connected clusters.
        if not self._manager.has(name):
            resolved = self._resolve_peer_cluster(name)
            if resolved:
                logger.warning(f"cluster.send: brain used peer handle '{name}' as cluster name → "
                               f"rerouted to cluster '{resolved}'")
                name = resolved
            else:
                _b._emit("error", f"cluster.send: unknown cluster '{name}' (connected: "
                      f"{', '.join(self._manager.names()) or 'none'})")
                return
        # SALVAGE: a malformed JSON tag body (newlines, unescaped quotes) would LOSE the real message. Pull a
        # "text":"…" from the raw body, else use the raw as plain text: a best-effort recipient beats silence.
        raw = (extra.get("raw") or "").strip()
        if not (text or "").strip() and raw:
            import re as _re
            mt = _re.search(r'"text"\s*:\s*"(.*?)"\s*(?:,|\})', raw, _re.S)
            text = (mt.group(1).replace('\\n', '\n').replace('\\"', '"') if mt
                    else (raw if not raw.lstrip().startswith("{") else ""))
            if not to:
                mto = _re.search(r'"to"\s*:\s*"(.*?)"', raw)
                to = mto.group(1) if mto else to
            if text:
                logger.warning(f"cluster.send: salvaged text from malformed JSON ({name})")
        # Outbound guard: NOTHING leaves for the cluster unscanned. A hard secret (token/key/IBAN/card)
        # blocks the whole message; identity/model terms are redacted in place. See connectors/meshkore/security.py.
        text, blocked = security.scan_outbound(text or "")
        if blocked:
            journal.record({"chan": "out", "action": "cluster.send", "blocked": blocked, "cluster": name})
            _b._emit("error", f"cluster {name}: outbound blocked — possible secret leak ({blocked}). Not sent.")
            return
        # RESOURCE GUARD (V2-071): a large CODE DUMP through the channel is never the right pattern (code is
        # collaborated on through the repository, not pasted into chat — and it is the largest token sink).
        # Replace it with a repo pointer, like redacting a secret. Always active; a small snippet passes intact.
        text, code_stripped = security.guard_code_outbound(text, accum_key=f"{name}:{to or '*'}")
        if code_stripped:
            _b._emit("resource", f"⚖ {name}·{to or '*'}: volcado de código → puntero al repo",
                  extra={"cluster": name, "to": to or "*", "dir": "out", "code_stripped": True})
        # Attachments are ANOTHER outbound channel: a secret can ride in media[].url / b64. Scan them with
        # the same policy or the text scan above is cosmetic (audit V3). A hard secret blocks the whole msg.
        media, mblocked = security.scan_media_outbound(data.get("media"))
        if mblocked:
            journal.record({"chan": "out", "action": "cluster.send", "blocked": mblocked, "cluster": name})
            _b._emit("error", f"cluster {name}: outbound blocked — possible secret leak ({mblocked}). Not sent.")
            return
        if not extra.get("confirmed") and send_gate.gate(name, to, text, media) != "send":
            return                       # V2-805: his consent rule for this channel held or refused it
        # AGREED CADENCE (V2-072): if this relationship has an agreed cadence, WAIT for the remaining time
        # before sending another message — no bursts. This is the REAL enforcement of zalo's complaint
        # (we were bombarding it). Off the voice path -> sleeping here blocks nothing critical. Defensive cap.
        if to:
            try:
                _ph = security.neutralize_identity(to)
                wait = capsule.cadence_wait(capsule.load(name, _ph), self._now())
                if wait > 0:
                    _b._emit("cluster", f"⏳ {name}·{to}: cadencia pactada, espero {wait:.0f}s",
                          extra={"cluster": name, "to": to, "cadence_wait": round(wait, 1)})
                    await asyncio.sleep(min(wait, capsule.CADENCE_MAX_S))
            except Exception:
                pass
        await self._manager.send(name, to=to, text=text, media=media)
        self._engaged[name] = True
        self._last_activity[name] = self._now()
        self._nudged.discard(name)
        if to:                                   # seal when we sent, for the next cadence check
            try:
                capsule.patch(name, security.neutralize_identity(to), last_out_ts=self._now())
            except Exception:
                pass
        _b._emit("cluster", f"⇢ {name}·{to or '*'}", text=text, role="assistant",
              extra={"cluster": name, "to": to or "*", "dir": "out"})
        self._notify_registry()
        return text        # what actually went to the peer (post-guard) → passive memory observation


# Shared state is read through the facade module object, so a patch of `connectors.meshkore.bridge.<name>` is seen here.
from connectors.meshkore import bridge as _b  # noqa: E402
