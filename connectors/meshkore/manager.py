#
# MeshKoreManager — the native, brain-agnostic hub for ALL cluster connections.
#
# zaelar can be subscribed to 1..N MeshKore clusters at once (each its own WS via MeshKoreClient). The manager
# owns that registry, exposes connect/disconnect/send, and funnels every inbound frame from every cluster into a
# SINGLE async sink (set by the bridge). Nothing here knows about Hermes or any brain — this is pure I/O.
#
import os

from loguru import logger

from connectors.meshkore.client import MeshKoreClient
from connectors.meshkore import identity

DEFAULT_HANDLE = os.getenv("MESHKORE_AGENT_HANDLE", "zaelar")


class MeshKoreManager:
    def __init__(self):
        self._clients: dict[str, MeshKoreClient] = {}
        self._sink = None   # async callable(event: dict) — the bridge

    def set_sink(self, sink):
        self._sink = sink

    async def _on_event(self, event: dict):
        if self._sink:
            await self._sink(event)

    async def connect(self, name: str, cluster_id: str, token: str,
                      handle: str = None, did: str = None, vis: str = "") -> MeshKoreClient:
        """Open (or replace) the connection aliased `name`. `vis="public"` = cluster abierto sin token (V2-086)."""
        if name in self._clients:
            await self.disconnect(name)
        did = did or identity.did_key()          # stable did:key so peers recognise zaelar (auto, no brain input)
        client = MeshKoreClient(name, cluster_id, token, handle or DEFAULT_HANDLE,
                                did, on_event=self._on_event, vis=vis)
        self._clients[name] = client
        await client.start()
        logger.info(f"MeshKore: connecting cluster '{name}' ({cluster_id[:8]}…) as {did[:24]}…")
        return client

    async def disconnect(self, name: str):
        client = self._clients.pop(name, None)
        if client:
            await client.stop()
            logger.info(f"MeshKore: disconnected cluster '{name}'")

    async def send(self, name: str, to: str = None, text: str = None,
                   media: list = None, payload=None):
        client = self._clients.get(name)
        if not client:
            raise RuntimeError(f"MeshKore: no cluster '{name}' (connect first)")
        # Canonical §4 content convention: payload is a BARE STRING for plain text (the default), or an object
        # {text, media:[{mime, url|b64}]} for text + attachments. NEVER invent type/ack/in_reply_to fields, and
        # NEVER put from/to in the content — the transport frame carries them (from = our handle, to = recipient).
        if payload is not None:
            body = payload                                   # caller passed an explicit shape (rare)
        elif media:
            body = {"text": text or "", "media": media}       # text + attachments in one message
        else:
            body = (text or "").strip()                       # plain text
        # DROP empty sends: a malformed/empty [[cluster.send]] tag (bad JSON, missing text) would otherwise go out
        # as a `{}` broadcast — the empty-message spam Ricard saw. Never emit a frame with no content.
        empty = (not body) or (isinstance(body, dict) and not (body.get("text") or body.get("media")))
        if empty:
            logger.warning(f"MeshKore: dropped EMPTY send to {to or '*'} on '{name}' (no text/media)")
            return
        await client.send(to, body)

    def get(self, name: str) -> MeshKoreClient | None:
        return self._clients.get(name)

    def has(self, name: str) -> bool:
        return name in self._clients

    def names(self) -> list[str]:
        return list(self._clients)

    def clusters(self) -> list[dict]:
        """Snapshot para el endpoint de estado, el brief del cerebro y la pestaña nativa «Clusters» (V2-086).

        Incluye los clusters de los que hay CREDENCIALES GUARDADAS aunque no haya cliente vivo — un cluster que
        el operador dio de alta pero está caído debe VERSE como «desconectado», no desaparecer de la lista (era
        el comportamiento anterior: solo se listaba `self._clients`, así que un fallo de conexión lo volvía
        invisible justo cuando más falta hacía saber que existe).

        Nunca expone el token: solo `public` (si el cluster es abierto) y el `cluster_id`, que no es secreto —
        viaja en la propia URL de invitación."""
        rows, seen = [], set()
        for c in self._clients.values():
            seen.add(c.name)
            rows.append({"name": c.name, "connected": c.connected, "handle": c.handle,
                         "online": sorted(c.online), "cluster_id": c.cluster_id, "public": c.public,
                         "msgs_in": c.msgs_in, "msgs_out": c.msgs_out,
                         "msgs": c.msgs_in + c.msgs_out})
        try:
            from connectors.meshkore import store
            for name, cfg in (store.load_clusters() or {}).items():
                if name in seen:
                    continue
                rows.append({"name": name, "connected": False, "handle": cfg.get("handle", "zaelar"),
                             "online": [], "cluster_id": cfg.get("cluster_id", ""),
                             "public": (cfg.get("vis", "") == "public") or not cfg.get("token"),
                             "msgs_in": 0, "msgs_out": 0, "msgs": 0})
        except Exception:
            pass
        return rows

    async def shutdown(self):
        for name in list(self._clients):
            await self.disconnect(name)
