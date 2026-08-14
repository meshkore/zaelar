#
# client.py — HTTP client (loopback) for the vendored Baileys bridge (connectors/whatsapp/bridge/).
#
# The bridge binds ONLY 127.0.0.1 and validates the Host header (anti DNS-rebind). Endpoints used in INI-014
# (read-only + mark-read): GET /messages (drains inbound queue), POST /mark-read (marks read), GET /health. We do
# NOT use /send in this initiative (autoresponder is Phase 4, with separate go-ahead).
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
    """Return (and clear) the inbound-message queue accumulated since the last poll."""
    msgs = await _request("GET", "/messages")
    return msgs or []


async def mark_read(keys: list[dict]) -> dict:
    """Mark the indicated messages as read. Each key: {chatId, messageId, senderId?}."""
    if not keys:
        return {"success": True, "marked": 0}
    return await _request("POST", "/mark-read", body={"keys": keys})
