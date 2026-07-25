#
# ClusterBridge — the seam between the MeshKore transport and the BRAIN.
#
# It does NOT think. It (1) turns every inbound cluster frame into a labelled brain input, (2) runs that through
# the injected `reasoner` (the active brain, off the voice pipeline), (3) parses the reply's [[cluster.*]] tags
# and routes them back to the manager, and (4) keeps a lightweight "engaged" flag per cluster so a heartbeat can
# nudge the brain to follow up / conclude. All the decisions (what to say, when to wait, when to conclude) live
# in the brain. The reasoner serializes with the voice turn via the shared Hermes turn_lock, so a cluster turn
# never cuts off the operator mid-sentence.
#
import asyncio
import json
import os
import time

from loguru import logger

from voice.tag_protocol import strip_tags
from connectors.meshkore import brief, store, journal, security, mem_ingest, capsule

IDLE_SECS = float(os.getenv("MESHKORE_IDLE_SECS", "90"))    # engaged + silent this long → one nudge
TICK_SECS = float(os.getenv("MESHKORE_TICK_SECS", "20"))    # heartbeat cadence
MAX_INFLIGHT = int(os.getenv("MESHKORE_MAX_INFLIGHT", "8"))  # cap queued/in-flight brain turns → flood backpressure
# Anti-spam DEDUP (2026-07-25, live: zalo flooded 45 IDENTICAL "consultando con mi equipo… un momento" pings in
# ~90s — each spawned a brain turn until MAX_INFLIGHT dropped the rest, and zaelar burned tokens replying
# "Entendido, quedo a la espera" 40×). A peer re-sending the EXACT same text within this window is a loop/spam,
# not a new turn: reply ONCE, ignore verbatim repeats. Defensive hardening on the untrusted channel, same spirit
# as MAX_INFLIGHT — does NOT change conversational style, only suppresses reacting to duplicate spam.
DEDUP_SECS = float(os.getenv("MESHKORE_DEDUP_SECS", "60"))
_REGISTRY_WIDGET = "cluster-registro"                       # widget to refresh on every cluster event


def _emit(*args, **kwargs):
    try:
        from voice.observer import emit
        emit(*args, **kwargs)
    except Exception:
        pass


import re as _re
import unicodedata as _ud

def _dedup_key(text: str) -> str:
    """Normalized key for anti-spam dedup: casefold + keep only alphanumerics and single spaces (drop emojis,
    punctuation, ellipsis variants, encoding differences). Two messages that reduce to the same key within
    DEDUP_SECS are the same status ping (a peer looping), not a distinct turn. '' for empty/no-alnum content
    (those bypass dedup — never suppress a real turn on a normalization artifact)."""
    n = _ud.normalize("NFKD", text or "").casefold()
    n = "".join(c for c in n if not _ud.combining(c))
    n = _re.sub(r"[^0-9a-z\s]+", " ", n)          # keep letters/digits/spaces only (ñ→n via NFKD above)
    return _re.sub(r"\s+", " ", n).strip()


class ClusterBridge:
    def __init__(self, manager, reasoner):
        self._manager = manager
        self._reasoner = reasoner            # async reasoner(text, on_chunk=None) -> str
        self._engaged: dict[str, bool] = {}  # cluster -> has an open joint task
        self._last_activity: dict[str, float] = {}
        self._nudged: set[str] = set()
        self._last_peer_msg: dict[str, str] = {}  # cluster -> most recent inbound text (idle-nudge context)
        self._caught_up: set[tuple] = set()   # (cluster, peer, last_in_ts) already nudged for catch-up (dedup)
        self._recent_inbound: dict[tuple, tuple] = {}  # (cluster,peer) -> (text, ts) for anti-spam verbatim dedup
        self._tick_task = None
        self._turns: set = set()             # keep brain-turn tasks alive

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────
    def start_heartbeat(self):
        if self._tick_task is None:
            self._tick_task = asyncio.create_task(self._heartbeat(), name="meshkore:heartbeat")

    async def stop(self):
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None

    def _now(self) -> float:
        return asyncio.get_event_loop().time()

    def note_objective(self, name: str, active: bool = True):
        """Mark a cluster as having an active joint objective (so a peer arriving wakes the brain). Used by the
        startup autoreconnect path, which connects saved clusters directly (bypassing the [[cluster.connect]] tag).
        v1 caveat: a task concluded with [[cluster.done]] before a restart re-engages here (mission state isn't
        persisted yet) — the operator can just say 'stop'."""
        self._engaged[name] = active
        self._last_activity[name] = self._now()

    def _notify_registry(self):
        """Touch the cluster-registro widget store so SSE fires → canvas re-renders with the latest log data."""
        try:
            from widgets import store as wstore
            wstore.save(_REGISTRY_WIDGET, {"_tick": time.time_ns()})
        except Exception:
            pass

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
            return None                                    # ya contestado (o después)
        key = (cluster, peer, ts)
        if key in self._caught_up:
            return None
        self._caught_up.add(key)
        return ex.get("last_in_text") or ""

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

    def _spawn(self, coro):
        # Flood backpressure: turns serialize on the shared turn_lock, so a peer spamming messages would otherwise
        # queue unbounded brain turns (memory + guaranteed LLM-cost DoS). Above the cap we DROP the new turn (a peer
        # cannot force unbounded work) and alert the operator once. Prefer dropping over unbounded acceptance.
        if len(self._turns) >= MAX_INFLIGHT:
            coro.close()
            _emit("error", f"cluster: dropped a brain turn — {MAX_INFLIGHT} already queued (flood backpressure).")
            return
        t = asyncio.create_task(coro)
        self._turns.add(t)
        t.add_done_callback(self._turns.discard)

    # ── inbound: manager sink ──────────────────────────────────────────────────────────────────────────────
    async def on_event(self, ev: dict):
        """Every frame from every cluster lands here (see MeshKoreClient._emit)."""
        journal.record({"chan": "in", **ev})                     # full post-mortem trail (redacted)
        # MeshKore tags frames with "kind" (message/ready/presence/ack/error); keep "type" as a fallback.
        t = ev.get("kind") or ev.get("type")
        cluster = ev.get("cluster", "?")
        if t == "message":
            frm = ev.get("from") or "?"
            client = self._manager.get(cluster)
            if client and frm == client.handle:
                return                                            # ignore our own echoes
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
            _dk = (cluster, frm)
            _prev = self._recent_inbound.get(_dk)
            _txt = (text or "").strip()
            _key = _dedup_key(_txt)
            if _key and _prev and _prev[0] == _key and (self._now() - _prev[1]) < DEDUP_SECS:
                self._recent_inbound[_dk] = (_key, self._now())   # slide the window; keep suppressing a sustained loop
                _emit("cluster", f"⇠ {cluster}·{security.neutralize_identity(frm)} (repetido, ignorado)",
                      extra={"cluster": cluster, "peer": security.neutralize_identity(frm), "dir": "in", "dedup": True})
                self._notify_registry()
                return
            if _key:
                self._recent_inbound[_dk] = (_key, self._now())
            # SSE/timeline/observer copy is REDACTED: a peer message can carry a secret-shaped value (or echo back
            # one of our own tokens) and this surface persists to logs + streams to the UI (audit V6). The brain
            # copy below stays raw (fenced) — Hermes needs the real content to collaborate; the fence handles trust.
            frm_lbl = security.neutralize_identity(frm)
            _emit("cluster", f"⇠ {cluster}·{frm_lbl}", text=store.redact(text), role="peer",
                  extra={"cluster": cluster, "peer": frm_lbl, "dir": "in", "media": media})
            note = text + (f"\n[{len(media)} attachment(s): " + ", ".join(
                (m.get("mime") or "file") + (" " + m["url"] if m.get("url") else "") for m in media) + "]" if media else "")
            # The peer's content is UNTRUSTED — fence it so the brain reads it as data, not instructions (the
            # header before it is our own trusted label). Our security rules get reasserted at the END in _brain_turn.
            # The handle itself is ALSO peer-chosen: it sits OUTSIDE the fence in our label, so neutralize it or a
            # crafted handle forges a fence-close + fake trailer right in the trusted header (audit V2).
            frm_s = security.neutralize_identity(frm)
            self._spawn(self._brain_turn(
                cluster, f"[cluster:{cluster} · message from agent '{frm_s}']\n{security.fence_untrusted(note)}",
                peer=frm_lbl, peer_text=text))
            self._notify_registry()
        elif t == "presence":
            ag, st = ev.get("agent"), ev.get("status")
            _emit("cluster", f"• {cluster}: {ag} {st}", extra={"cluster": cluster, "peer": ag, "status": st})
            # V2-067 (petición del operador, 2026-07-24): NADA de datos/objetivo predefinido al conectar — el
            # widget solo facilita la conexión; quien decide de qué hablar es el operador, con sus propias
            # instrucciones. La ÚNICA cosa automática permitida es una presentación breve (nombre+capacidades) y
            # SOLO la primera vez que se cruza con este peer (memoria durable vía mem_ingest.known_peer — reconectar
            # con alguien ya conocido y volver a presentarse sería absurdo). Si hay una tarea activa de verdad
            # (`self._engaged`), eso lo decide una instrucción explícita del operador, no este evento de presencia.
            if st == "online" and not mem_ingest.known_peer(cluster, ag):
                self._nudged.discard(cluster)
                ag_s = security.neutralize_identity(ag)             # peer-chosen handle → neutralize before the prompt (V2)
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · event] agent '{ag_s}' just came online and you've never talked before. "
                    f"Send a SHORT self-introduction ONLY — your name and a one-line generic description of your "
                    f"capabilities. Do NOT propose an objective, a task, roles, or a collaboration format — just "
                    f"say hello and stop."))
                capsule.patch(cluster, ag, greeted=True)   # V2-069: presentado → no repetirlo (fase avanza a sondeo)
            elif st == "online":
                # conocido → sin intro, pero puede tener un mensaje sin contestar de cuando estuvimos offline
                # (petición del operador 2026-07-25: "hay mensajes que nos han mandado pero no hemos contestado").
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
            _emit("cluster", f"✓ joined {cluster}", extra={"cluster": cluster, "online": online})
            # V2-067: mismo criterio que arriba — solo se presenta a los peers que NUNCA ha visto en este cluster,
            # nunca abre una "colaboración" ni propone un objetivo por su cuenta. Si TODOS los presentes ya son
            # conocidos, se queda callado (evita el "hola de nuevo" absurdo en cada reconexión).
            unknown = [p for p in online if not mem_ingest.known_peer(cluster, p)]
            if unknown:
                self._last_activity[cluster] = self._now()
                self._nudged.discard(cluster)
                unknown_s = ", ".join(security.neutralize_identity(h) for h in unknown)   # peer handles → neutralize (V2)
                self._spawn(self._brain_turn(
                    cluster,
                    f"[cluster:{cluster} · event] you just connected; agent(s) online you've never talked to before: "
                    f"{unknown_s}. Send a SHORT self-introduction ONLY — your name and a one-line generic "
                    f"description of your capabilities. Do NOT propose an objective, a task, roles, or a "
                    f"collaboration format — just say hello and stop."))
                for _p in unknown:
                    capsule.patch(cluster, _p, greeted=True)   # V2-069: presentado → fase avanza, no re-presentarse
            # CATCH-UP (petición del operador 2026-07-25): un peer YA CONOCIDO puede habernos escrito mientras
            # estábamos desconectados (a veces días) — MeshKore no tiene historial de servidor (client.py: relay
            # a quien esté conectado AHORA), así que si nadie retoma esos mensajes al reconectar, se pierden en
            # silencio para siempre. Uno por peer conocido, cada uno con su propio contexto/trace.
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
            _emit("cluster", f"{cluster}: {ev.get('status')}", extra={"cluster": cluster, "status": ev.get("status")})
            self._notify_registry()
        elif t == "ack":
            if ev.get("delivered") == 0:
                _emit("cluster", f"⚠ {cluster}: recipient offline", extra={"cluster": cluster})
                self._notify_registry()
        elif t == "error":
            _emit("error", f"cluster {cluster}: {store.redact(json.dumps(ev, ensure_ascii=False))}")
            self._notify_registry()

    # ── the brain turn (off the voice pipeline) ──────────────────────────────────────────────────────────────
    async def _brain_turn(self, cluster: str, event_text: str, peer: str | None = None,
                          peer_text: str | None = None):
        # TRAZABILIDAD (V2-044): un mensaje de peer también es un estímulo → nace con su trace (origin="cluster").
        # _brain_turn corre como task propia (create_task) → el ctxvar queda acotado a este turno.
        try:
            from voice import trace as _trace
            _trace.begin((peer_text or event_text or "")[:200], origin="cluster")
        except Exception:
            pass
        # CÁPSULA (V2-069 «una sola mente»): la mente se SITÚA en la relación antes de responder — quién es el peer,
        # de qué habéis hablado, el objetivo, lo ya decidido y la FASE (que le dice, p.ej., NO re-presentarse en
        # trabajo/sondeo). Es la memoria-de-relación, NUESTRA (dossier destilado) — no texto crudo del peer. Sin
        # peer concreto (heartbeat/ready global) se omite. Va ANTES del evento y ANTES del trailer (nuestro prompt
        # de seguridad sigue yendo el último).
        rel_block = ""
        if peer:
            try:
                cap = capsule.load(cluster, peer)
                cap["phase"] = capsule.derive_phase(cap)
                rel_block = capsule.compose(cluster, peer, cap) + "\n\n"
            except Exception:
                rel_block = ""
        # Security rule of thumb: OUR prompt goes LAST. The trailer (do-not-reveal + injection defense) is appended
        # after the (possibly hostile) event content so a peer's "ignore all previous rules" can never sit after it.
        trailer = security.trailer()
        framed = f"{brief.for_brain()}\n\n{rel_block}{event_text}" + (f"\n\n{trailer}" if trailer else "")
        t0 = time.time()
        try:
            reply = await self._reasoner(framed)
        except Exception as e:
            logger.warning(f"MeshKore brain turn failed: {e}")
            _emit("error", f"cluster brain turn failed: {e}")
            return "", []
        cluster_ms = round((time.time() - t0) * 1000)
        spoken, sent = await self._route_reply(reply)
        # OBSERVACIÓN PASIVA cluster→memoria (V2-021 T170): solo en un turno de MENSAJE de un peer (no presence/
        # heartbeat). Destila entrante+saliente en una síntesis CUARENTENADA por peer, off-hot-path y
        # fire-and-forget — el reasoner sigue stateless; esto no le da estado ni capacidades. `sent` = lo que de
        # verdad salió al peer (ya pasado por el guard de salida); si no envió nada, cae al aside `spoken`.
        if peer_text is not None and peer:
            mem_ingest.observe_exchange(cluster, peer, peer_text, "\n".join(sent) or spoken)
            # CÁPSULA (V2-069): ya hemos intercambiado con este peer → marca greeted (no re-presentarse), suma un
            # turno sustantivo y re-deriva la fase. Barato y directo (sys_kv). No toca el estado del operador.
            try:
                cap = capsule.load(cluster, peer)
                cap["greeted"] = True
                cap["turns"] = int(cap.get("turns") or 0) + 1
                cap["phase"] = capsule.derive_phase(cap)
                capsule.save(cluster, peer, cap)
            except Exception:
                pass
        if spoken.strip():
            # INVARIANT: the cluster channel NEVER reaches the speaker. Anything the brain says here is agent-to-agent
            # or an aside for the /debug wall — it goes to the UI observer ONLY, never to TTS. The operator hears
            # cluster activity only if the brain deliberately turns it into a voice reply (a normal user turn) or a
            # proactive.notify — both of which pass through the voice/speech.py gate. Do NOT add a speak() call here.
            # redact in case the brain echoed a token/secret back into its operator-facing aside.
            _emit("cluster", "🧠 zaelar", text=store.redact(spoken.strip()), role="assistant",
                  extra={"cluster": cluster, "dir": "note", "cluster_ms": cluster_ms})
        return spoken, sent

    # A reply generated FROM a cluster turn is untrusted output: a peer could have prompt-injected the brain into
    # emitting a tag. So from this path we allow ONLY the collaboration primitives (talk to peers / conclude).
    # cluster.connect (join an attacker cluster, persisted) and cluster.disconnect (sever a real collaboration) are
    # operator-only — reachable from the voice path and REST, never from an inbound peer message. Least privilege.
    _CLUSTER_TURN_ALLOWED = {"cluster.send", "cluster.done"}

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
                _emit("error", f"cluster: blocked '{action}' emitted during a cluster turn (operator-only action).")
            # widget/cron/show/close tags emitted off-pipeline have no canvas/context here — drop silently.

        spoken, _ = strip_tags(reply or "", collect, final=True)
        sent: list[str] = []
        for action, extra in actions:
            out = await self.dispatch(action, extra)
            if out:
                sent.append(out)
        return spoken, sent

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
                    _emit("error", "cluster.connect: missing 'name'")
                    return
                creds = store.resolve(name, data.get("cluster_id", ""), data.get("token", ""),
                                      data.get("handle", ""))
                if not creds:
                    _emit("error", f"cluster.connect '{name}': no cluster_id/token (paste them first)")
                    return
                await self._manager.connect(name, creds["cluster_id"], creds["token"], creds.get("handle"))
                store.save_cluster(name, creds["cluster_id"], creds["token"], creds.get("handle", "zaelar"))
                # Connecting = there's an active objective on this cluster. Marking it engaged NOW means a peer
                # arriving later (presence:online) wakes the brain to open the collaboration, even if we joined an
                # empty channel and haven't sent anything yet. Cleared by [[cluster.done]]/[[cluster.disconnect]].
                self._engaged[name] = True
                self._last_activity[name] = self._now()
                _emit("cluster", f"→ connecting {name}", extra={"cluster": name})
            elif action == "cluster.send":
                name = extra.get("name") or ""
                data = extra.get("data") or {}
                to, text = data.get("to"), data.get("text", "")
                # RESILIENT NAME RESOLUTION: the brain sometimes emits [[cluster.send:<peer_handle>]] instead of
                # [[cluster.send:<cluster_name>]] (confusing <cluster_name> with the peer's handle). Fix silently:
                # if no cluster matches `name`, try resolving it as a peer handle across all connected clusters.
                if not self._manager.has(name):
                    resolved = self._resolve_peer_cluster(name)
                    if resolved:
                        logger.warning(f"cluster.send: brain used peer handle '{name}' as cluster name → "
                                       f"rerouted to cluster '{resolved}'")
                        name = resolved
                    else:
                        _emit("error", f"cluster.send: unknown cluster '{name}' (connected: "
                              f"{', '.join(self._manager.names()) or 'none'})")
                        return
                # SALVAGE: deepseek/others sometimes emit malformed JSON in the tag (newlines, unescaped quotes) →
                # parse_json returns None → data empty → zaelar's real message would be LOST. Recover the text from
                # the raw tag body: pull a "text":"…" if present, else use the raw as plain text (it's still the
                # message the brain wanted to send). Better a message with a best-effort recipient than silence.
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
                    _emit("error", f"cluster {name}: outbound blocked — possible secret leak ({blocked}). Not sent.")
                    return
                # Attachments are ANOTHER outbound channel: a secret can ride in media[].url / b64. Scan them with
                # the same policy or the text scan above is cosmetic (audit V3). A hard secret blocks the whole msg.
                media, mblocked = security.scan_media_outbound(data.get("media"))
                if mblocked:
                    journal.record({"chan": "out", "action": "cluster.send", "blocked": mblocked, "cluster": name})
                    _emit("error", f"cluster {name}: outbound blocked — possible secret leak ({mblocked}). Not sent.")
                    return
                await self._manager.send(name, to=to, text=text, media=media)
                self._engaged[name] = True
                self._last_activity[name] = self._now()
                self._nudged.discard(name)
                _emit("cluster", f"⇢ {name}·{to or '*'}", text=text, role="assistant",
                      extra={"cluster": name, "to": to or "*", "dir": "out"})
                self._notify_registry()
                return text        # what actually went to the peer (post-guard) → passive memory observation
            elif action == "cluster.done":
                name = extra.get("name") or ""
                if not self._manager.has(name):
                    resolved = self._resolve_peer_cluster(name)
                    if resolved:
                        name = resolved
                if self._manager.has(name):
                    self._engaged[name] = False
                    _emit("cluster", f"✔ {name}: task concluded", extra={"cluster": name})
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
            _emit("error", f"cluster {action} failed: {e}")

    def _heartbeat_context(self, cluster: str) -> str:
        """Best-effort 'what was the peer last saying' for the idle nudge below, so the reasoner isn't asked to
        decide blind. Prefers the live in-process text from THIS run; falls back to the durable per-peer synthesis
        (`mem_ingest`, survives a restart) — same untrusted-peer content the reasoner already sees on every
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
        ZERO context — the reasoner was asked to "decide: follow up, or conclude" with no idea what the peer last
        said, so a peer's "one moment, checking with my team" got answered with [[cluster.done]] (conversation
        closed while the peer was still actively working). Fixed by feeding it the last known message/topic.

        That fix uncovered a SECOND bug: `_nudged` used to be marked permanently on every heartbeat firing,
        regardless of outcome — so once the reasoner (correctly) chose to stay silent and wait, the cluster went
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
        _, sent = await self._brain_turn(cluster, event_text)
        if not sent and self._engaged.get(cluster):
            self._last_activity[cluster] = self._now()   # re-arm: check again after another idle stretch
            self._nudged.discard(cluster)

    # ── heartbeat: nudge on idle-with-peers-present (human-like follow-up), never spam ──────────────────────
    async def _heartbeat(self):
        while True:
            try:
                await asyncio.sleep(TICK_SECS)
                now = self._now()
                for cluster, engaged in list(self._engaged.items()):
                    if not engaged or cluster in self._nudged:
                        continue
                    client = self._manager.get(cluster)
                    if not client or not client.online:          # no peers → wait silently (human-like)
                        continue
                    if now - self._last_activity.get(cluster, 0) < IDLE_SECS:
                        continue
                    self._nudged.add(cluster)                     # suppress re-entry WHILE this turn is in flight
                    self._spawn(self._heartbeat_nudge(cluster))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"MeshKore heartbeat: {e}")
