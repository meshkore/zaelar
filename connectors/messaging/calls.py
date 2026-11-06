"""What a messaging connector did with the outside world, ONE observer row each (capture gaps, 2026-11-06).

Until this, a message that arrived left no event at the moment it arrived — it showed only when the pulse spoke it
(`notify 🔔`) — and a send left a card op and, when it failed, an `action_failed`; the connector call itself, with its
result and how long it took, was nowhere. Both surfaces (the engine's ◷ viewer and the operator console) read kind `connector`:

    📨 <platform>                  op=inbound · from · chat · group · subject · message_id · attachments · text=excerpt
    📤 <platform> · reply|send     op · ok · ms · to · ref · files · error

The excerpt is bounded (`EXCERPT`) and scrubbed (`observability/scrub`): the record says WHAT came and from whom, never the whole letter — the content is
his and lives in his card. No credential, no header beyond sender and subject. Never raises, never waits: a row that
cannot be written is not a message that did not arrive.
"""
from __future__ import annotations

from loguru import logger

EXCERPT = 160
_HANDLE = 120


def _s(v, n: int = _HANDLE) -> str:
    return " ".join(str(v or "").split())[:n]


def inbound(platform: str, msg: dict) -> None:
    """A normalized inbound message (`ingest.publish_msg`'s shape) just handed to the bus."""
    try:
        m = msg or {}
        extra = {"platform": str(platform), "op": "inbound", "ok": True,
                 "from": _s(m.get("senderName") or m.get("from") or m.get("senderId") or m.get("chatId")),
                 "group": bool(m.get("isGroup"))}
        for key, field in (("chatName", "chat"), ("subject", "subject"), ("messageId", "message_id")):
            if m.get(key):
                extra[field] = _s(m.get(key))
        atts = m.get("attachments") or m.get("media") or []
        if atts:
            extra["attachments"] = len(atts) if isinstance(atts, (list, tuple)) else 1
        from voice.observer import emit
        from observability.scrub import scrub           # a code or a token in a message never reaches the record
        emit("connector", f"📨 {platform}", text=scrub(_s(m.get("body") or m.get("text"), EXCERPT)), role="system",
             extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"connector: inbound {platform} not recorded ({e!r})")


def sent(platform: str, op: str, *, ok: bool, ms: int, to="", ref="", files: int = 0, error="") -> None:
    """A send the connector made (`op` = reply | send): whether it left, how long the provider took, to which handle,
    for which order (`ref`), and the failure's cause when it did not leave."""
    try:
        extra = {"platform": str(platform), "op": str(op), "ok": bool(ok), "ms": int(ms or 0)}
        if to:
            extra["to"] = _s(to)
        if ref:
            extra["ref"] = _s(ref, 80)
        if files:
            extra["files"] = int(files)
        if not ok:
            extra["error"] = _s(error, 200) or "failed"
        from voice.observer import emit
        emit("connector", f"📤 {platform} · {op} · {'✅' if ok else '⚠️'}", role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"connector: {platform} {op} not recorded ({e!r})")
