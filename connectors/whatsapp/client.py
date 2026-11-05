#
# client.py — HTTP client (loopback) for the vendored Baileys bridge (connectors/whatsapp/bridge/).
#
# The bridge binds ONLY 127.0.0.1 and validates the Host header (anti DNS-rebind). Endpoints used
# (read-only + mark-read): GET /messages (drains inbound queue), POST /mark-read (marks read), GET /health. We do
# NOT use /send in this initiative (autoresponder is Phase 4, with separate go-ahead).
#
import aiohttp

from connectors.whatsapp import config


class BridgeError(RuntimeError):
    """The bridge ANSWERED with an error: `status` is its HTTP status, `error` its own sentence."""

    def __init__(self, msg: str, *, status: int = 0, error: str = ""):
        super().__init__(msg)
        self.status = int(status or 0)
        self.error = str(error or "")


async def _request(method: str, path: str, *, body: dict | None = None, timeout: float = 15.0):
    to = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=to) as s:
        async with s.request(method, config.bridge_url() + path, json=body) as r:
            txt = await r.text()
            if r.status >= 400:
                err = ""
                try:
                    import json as _json
                    err = str((_json.loads(txt) or {}).get("error") or "")
                except Exception:  # noqa: BLE001 — not JSON: the raw text is the sentence
                    err = txt[:200]
                raise BridgeError(f"{method} {path} → {r.status}: {txt[:200]}", status=r.status, error=err)
            return await r.json() if txt else None


async def health() -> dict:
    return await _request("GET", "/health")


async def get_messages() -> list[dict]:
    """Return (and clear) the inbound-message queue accumulated since the last poll."""
    msgs = await _request("GET", "/messages")
    return msgs or []


async def send_message(chat_id: str, text: str, reply_to: str | None = None) -> dict:
    """Send a message through the bridge's POST /send (V2-521). `reply_to` threads it under the original.
    The bridge splits long texts itself and answers {success, messageId}. Sending is slower than a read —
    Baileys can take a while on a cold socket — hence the longer timeout."""
    body: dict = {"chatId": chat_id, "message": text}
    if reply_to:
        body["replyTo"] = reply_to
    return await _request("POST", "/send", body=body, timeout=45.0)


async def send_media(chat_id: str, path: str, caption: str = "") -> dict:
    """Send one file through the bridge's POST /send-media: an image, video or voice note goes as that kind (the
    bridge infers it from the extension), anything else as a document with its own name."""
    import os
    body = {"chatId": chat_id, "filePath": path, "fileName": os.path.basename(path).split("_", 2)[-1]}
    if caption:
        body["caption"] = caption
    return await _request("POST", "/send-media", body=body, timeout=120.0)


async def create_group(subject: str, participants: list[str]) -> dict:
    """Create a WhatsApp group with these JIDs: {id, subject}."""
    return await _request("POST", "/group", body={"subject": subject, "participants": participants}, timeout=60.0)


async def get_contacts() -> dict:
    """The address book the bridge has accumulated (V2-714). A SNAPSHOT, not a drain: WhatsApp cannot be
    asked for everything, so the same rows come back every pass and the import is idempotent by design."""
    return await _request("GET", "/contacts")


async def get_chats(before: float | None = None, limit: int = 20) -> dict:
    """One page of the chat book, newest first: {chats, complete, known}. The book starts at pairing — WhatsApp
    tells a linked device its chats once, then only what changes — so `complete` means «nothing older that this
    device was told about», not «the account's first chat»."""
    q = f"?limit={int(limit)}" + (f"&before={float(before)}" if before else "")
    return await _request("GET", "/chats" + q)


async def get_sync() -> list[dict]:
    """Return (and clear) up to 2000 messages of the history WhatsApp sent when this device was paired."""
    return await _request("GET", "/sync") or []


async def get_reads() -> list[dict]:
    """Return (and clear) the chats the operator read on ANOTHER device since the last poll (V2-546). Each
    entry: {chatId, at}. WhatsApp gives a per-chat counter, not a per-message watermark, so the bridge only
    queues one when that counter reaches zero."""
    reads = await _request("GET", "/reads")
    return reads or []


async def fetch_history(chat_id: str, oldest_id: str, oldest_ts: float, limit: int = 30,
                        oldest_from_me: bool = False, include_anchor: bool = False) -> dict:
    """Ask the operator's PHONE for messages older than the ones we hold (V2-546). It answers asynchronously —
    the messages arrive as ordinary upserts on the next poll — so the return value is only the acknowledgement,
    and `available: False` means this build or this phone cannot serve it."""
    return await _request("POST", "/history", timeout=30.0, body={
        "chatId": chat_id, "oldestId": oldest_id, "oldestTs": oldest_ts, "limit": limit,
        "oldestFromMe": bool(oldest_from_me), "includeAnchor": bool(include_anchor)})


async def mark_unread(key: dict) -> dict:
    """Put a chat back to unread on the phone, anchored on one of its messages: {chatId, messageId, senderId?, ts?}."""
    return await _request("POST", "/mark-unread", body={k: key.get(k) for k in ("chatId", "messageId", "senderId", "ts")})


async def mark_read(keys: list[dict]) -> dict:
    """Mark the indicated messages as read. Each key: {chatId, messageId, senderId?}."""
    if not keys:
        return {"success": True, "marked": 0}
    return await _request("POST", "/mark-read", body={"keys": keys})
