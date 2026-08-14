#
# MeshKore cluster WebSocket client — ONE persistent connection to ONE cluster.
#
# Protocol (https://meshkore.com/cluster/protocol): a single WS carries everything.
#   URL     wss://api.meshkore.com/v1/clusters/{cluster_id}/ws?token=…&agent={handle}&did={did:key}
#   send    {"to": "<handle>|omit-for-broadcast", "payload": {...}}   (≤ 64 KB)
#   inbound frame types:
#     ready     {you, you_did, online:[...]}        — connection established + who's here
#     presence  {agent, did, status:"online|offline"}
#     message   {from, from_did, to, payload}
#     ack       {to, delivered:0|1}                 — send receipt (0 ⇒ recipient offline)
#     error     {...}
# No message history (relay to whoever is connected now). No app-level heartbeat — we rely on WS ping/pong.
#
# This class is pure transport: it knows nothing about brains. It forwards every inbound frame (annotated with
# the cluster alias) to an async `on_event` sink; the MeshKoreManager wires that sink to the bridge.
#
import asyncio
import json
import os
import urllib.parse

from loguru import logger
from websockets.asyncio.client import connect

WS_BASE = os.getenv("MESHKORE_WS_BASE", "wss://api.meshkore.com/v1")
MAX_FRAME = 64 * 1024   # protocol size limit


class MeshKoreClient:
    def __init__(self, name: str, cluster_id: str, token: str, handle: str = "zaelar",
                 did: str = None, on_event=None, vis: str = ""):
        self.name = name                # local alias for this cluster
        self.cluster_id = cluster_id
        self._token = token
        self.handle = handle
        self._did = did
        self._vis = (vis or "").strip().lower()   # "public" → OPEN cluster, no token (V2-086)
        self._on_event = on_event       # async callable(event: dict)
        self._ws = None
        self._task = None
        self._closing = False
        self.online: set[str] = set()   # handles currently present (excludes us)
        self.connected = False
        # TRAFFIC counters (V2-086) — the only volume data the native «Clusters» tab needs. Deliberately do NOT store
        # conversations: clusters already have their own monitor, and replicating history here would only duplicate
        # state (operator decision). Counting is cheap and retains no content.
        self.msgs_in = 0
        self.msgs_out = 0

    @property
    def public(self) -> bool:
        """PUBLIC cluster (tokenless). Inferred from `vis=public` or, failing that, from having no token: the
        distinction is real in the protocol, not cosmetic — it changes the connection query."""
        return self._vis == "public" or not self._token

    def _url(self) -> str:
        """Connection query. TWO modes (V2-086):
          · PRIVATE — `?token=…&agent=…`  (as before: credential authorizes).
          · PUBLIC  — `?agent=…&vis=public` (MeshKore Commons and similar: no token, choose your handle).
        Sending EMPTY `token=` on a public cluster is not equivalent: the server interprets it as a failed auth
        attempt, not as anonymous entry. That is why the key is OMITTED, not sent blank."""
        q = {"agent": self.handle}
        if self.public:
            q["vis"] = self._vis or "public"
        else:
            q["token"] = self._token
        if self._did:
            q["did"] = self._did
        return f"{WS_BASE}/clusters/{self.cluster_id}/ws?" + urllib.parse.urlencode(q)

    async def start(self):
        """Spawn the connect/read loop (reconnects with backoff until stop())."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"meshkore:{self.name}")

    @staticmethod
    def _classify(e: Exception) -> tuple[str, str]:
        """Turn a connection exception into (reason, detail) so the debook says WHY it failed — auth rejected
        (HTTP 401/403), kicked (server close code), or a network problem. The detail is REDACTED: a connection
        exception (or a server close reason) can embed the wss:// URL WITH the token in its string, and this
        detail lands in logs / the /debug timeline (audit V8)."""
        from connectors.meshkore import store
        name = type(e).__name__
        resp = getattr(e, "response", None)                       # websockets InvalidStatus → HTTP handshake reject
        code = getattr(resp, "status_code", None)
        if code is not None:
            return (("auth_rejected" if code in (401, 403) else "handshake_error"), f"HTTP {code}")
        rcvd = getattr(e, "rcvd", None) or getattr(e, "sent", None)   # ConnectionClosed → close frame
        cc = getattr(rcvd, "code", None)
        if cc is not None:
            reason = store.redact(getattr(rcvd, "reason", "") or "")
            return ("closed_by_server", f"close {cc}{': ' + reason if reason else ''}")
        if isinstance(e, (ConnectionRefusedError, TimeoutError, OSError)):
            return ("network", store.redact(f"{name}: {e}"))
        return ("error", store.redact(f"{name}: {e}"))

    async def _run(self):
        # TLS floor: refuse a plaintext ws:// endpoint (token travels in the query string → cleartext + MITM) unless
        # the operator explicitly opts in for local testing. Fail-closed: don't connect, surface why.
        if self._url().startswith("ws://") and os.getenv("MESHKORE_ALLOW_INSECURE", "0").strip().lower() \
                not in ("1", "true", "on", "yes"):
            logger.error(f"MeshKore[{self.name}]: refusing insecure ws:// endpoint "
                         "(set MESHKORE_ALLOW_INSECURE=1 to override for local testing)")
            self.connected = False
            await self._emit({"type": "status", "cluster": self.name, "status": "error",
                              "reason": "insecure_transport", "detail": "ws:// blocked (needs wss://)"})
            return
        backoff = 1.0
        while not self._closing:
            reason = detail = None
            try:
                # Keepalive tolerance: a brief loop-busy spike (cron tick, a brain turn) must NOT drop the link.
                # ping_timeout 60s (was 20) → far fewer spurious "keepalive ping timeout" closes; still auto-reconnects.
                async with connect(self._url(), ping_interval=30, ping_timeout=60,
                                    max_size=MAX_FRAME, open_timeout=20, close_timeout=10) as ws:
                    self._ws = ws
                    self.connected = True
                    backoff = 1.0
                    logger.info(f"MeshKore[{self.name}]: connected as '{self.handle}'")
                    async for raw in ws:
                        await self._handle(raw)
            except asyncio.CancelledError:
                break
            except Exception as e:
                reason, detail = self._classify(e)
                logger.warning(f"MeshKore[{self.name}]: {reason} ({detail})")
            finally:
                self._ws = None
                was = self.connected
                self.connected = False
                self.online.clear()
                ev = {"type": "status", "cluster": self.name, "was_connected": was,
                      "status": "disconnected" if reason is None else "error"}
                if reason:
                    ev["reason"], ev["detail"] = reason, detail
                # Journal DIRECTLY (independent of the bridge sink) so a first-attempt auth failure is never lost.
                try:
                    from connectors.meshkore import journal
                    journal.record(ev)
                except Exception:
                    pass
                if was or reason:                                 # a real event to surface (connected→dropped, or failed)
                    await self._emit(ev)
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _handle(self, raw):
        try:
            m = json.loads(raw)
        except Exception:
            return
        # The MeshKore server tags frames with "kind" (message/ready/presence/ack/…); keep "type" as a fallback.
        t = m.get("kind") or m.get("type")
        if t == "message":
            self.msgs_in += 1
        if t == "ready":
            self.online = {a for a in (m.get("online") or []) if a != self.handle}
        elif t == "presence":
            ag, st = m.get("agent"), m.get("status")
            if ag and ag != self.handle:
                (self.online.add if st == "online" else self.online.discard)(ag)
        # Forward EVERY frame (annotated) so the bridge decides what to do with it.
        await self._emit({**m, "cluster": self.name})

    async def _emit(self, event: dict):
        if self._on_event is None:
            return
        try:
            await self._on_event(event)
        except Exception as e:
            logger.warning(f"MeshKore[{self.name}]: sink error: {e}")

    async def send(self, to: str = None, payload: dict = None):
        """Send a frame. `to` = recipient handle, or None/'*' to broadcast to the whole cluster."""
        if not self._ws or not self.connected:
            raise RuntimeError(f"MeshKore[{self.name}] not connected")
        # Guard: never coerce an empty string to {} (that produced the empty `{}` broadcasts). Drop empties — the
        # manager already filters, this is defense-in-depth.
        if payload is None or payload == "" or payload == {}:
            return
        frame = {"payload": payload}
        if to and to != "*":
            frame["to"] = to
        data = json.dumps(frame)
        if len(data.encode("utf-8")) > MAX_FRAME:
            raise ValueError("MeshKore frame exceeds 64 KB limit")
        await self._ws.send(data)
        self.msgs_out += 1                                  # only after a REAL send (V2-086)

    async def stop(self):
        self._closing = True
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self.connected = False
