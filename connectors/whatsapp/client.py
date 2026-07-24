#
# client.py — cliente HTTP (loopback) del bridge Baileys vendorizado (connectors/whatsapp/bridge/).
#
# El bridge bindea SOLO 127.0.0.1 y valida el Host header (anti DNS-rebind). Endpoints que usamos en INI-014
# (read-only + mark-read): GET /messages (drena la cola de entrantes), POST /mark-read (marca leído), GET /health.
# NO usamos /send en esta iniciativa (el autorespondedor es Fase 4, con go-ahead aparte).
#
import aiohttp

from connectors.whatsapp import config


class BridgeError(RuntimeError):
    pass


async def _request(method: str, path: str, *, body: dict | None = None, timeout: float = 15.0):
    to = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=to) as s:
        async with s.request(method, config.bridge_url() + path, json=body) as r:
            txt = await r.text()
            if r.status >= 400:
                raise BridgeError(f"{method} {path} → {r.status}: {txt[:200]}")
            return await r.json() if txt else None


async def health() -> dict:
    return await _request("GET", "/health")


async def get_messages() -> list[dict]:
    """Devuelve (y vacía) la cola de mensajes entrantes acumulados desde el último poll."""
    msgs = await _request("GET", "/messages")
    return msgs or []


async def mark_read(keys: list[dict]) -> dict:
    """Marca como leídos los mensajes indicados. Cada key: {chatId, messageId, senderId?}."""
    if not keys:
        return {"success": True, "marked": 0}
    return await _request("POST", "/mark-read", body={"keys": keys})
