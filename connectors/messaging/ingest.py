#
# ingest.py — STATELESS messaging v2 "Hive" layer (EPIC-v2, V2-008). The central-diagram reshape: connectors stop
# TRIAGING and STORING state; they only READ their source and PUBLISH events to bus/ (Nervous System). Triage and
# the UI store move up to the `mensajeria` widget (owner backed), and durable CONTENT goes to central memory. The
# three signals that connect connector <-> widget live here:
#
#   • connector.msg     — a NORMALIZED inbound message (platform-agnostic payload), triaged by the widget.
#   • connector.status  — link state + QR for a platform, reflected by the widget in its card.
#   • msg.mark_read     — widget order to the right connector to mark-read in its app (routed by platform).
#
# STRANGLER-FIG: gated on BRAIN=nucleo. Under duo/hermes (the default until burial, V2-009), connectors keep their
# usual DIRECT path (service.py -> triage+store+notify), intact and live-verified. The v2 path runs in parallel,
# without regression, until cutover. See EPIC §2 (migration invariants).
#
import os

import bus

TOPIC_MSG = "connector.msg"
TOPIC_STATUS = "connector.status"
TOPIC_MARK_READ = "msg.mark_read"
TOPIC_REPLY = "msg.reply"          # V2-051: widget asks to SEND a reply; that platform's connector sends it


def v2_enabled() -> bool:
    """Is the stateless v2 path active? Follows the brain (nucleo -> yes) unless explicitly overridden by env
    (`ZAELAR_MSG_V2=0|1`, power-user fallback, NEVER configured by the end user). Connectors and the widget owner
    consult this single predicate to choose the path — zero divergence between pieces."""
    env = os.getenv("ZAELAR_MSG_V2")
    if env is not None:
        return env == "1"
    try:
        from config.v2 import active_brain
        return active_brain() == "nucleo"
    except Exception:
        return False


def publish_msg(platform: str, msg: dict) -> None:
    """Publish a normalized inbound message. `msg` = {senderName, chatName?, isGroup, body, messageId, chatId,
    senderId} (the SAME shape triage already understood). Loop-agnostic (emit_sync). Never raises."""
    try:
        bus.emit_sync(TOPIC_MSG, {"platform": platform, **(msg or {})})
    except Exception:
        pass


def publish_status(platform: str, status: str, qr=None, detail=None) -> None:
    """Publish a platform's link state + QR + human message (`detail`) (the widget reflects it in its card: loader
    with detail while connecting, error card with reason if it fails)."""
    try:
        bus.emit_sync(TOPIC_STATUS, {"platform": platform, "status": status, "qr": qr, "detail": detail})
    except Exception:
        pass


def publish_mark_read(key: dict) -> None:
    """Widget asks to mark-read: {platform, chatId, messageId, senderId}. That platform's connector drains it from
    its `MarkReadInbox` and marks it in its app."""
    try:
        bus.emit_sync(TOPIC_MARK_READ, dict(key or {}))
    except Exception:
        pass


def publish_reply(key: dict) -> None:
    """Widget asks to SEND a reply (V2-051): {platform, chatId, to, messageId, subject, msgid, text}. That platform's
    connector (email today) drains it from its `ReplyInbox` and sends it in its app (SMTP)."""
    try:
        bus.emit_sync(TOPIC_REPLY, dict(key or {}))
    except Exception:
        pass


class _PlatformInbox:
    """Base: per-platform subscription to a topic; drain() returns (and consumes) ONLY events for ITS platform. Each
    connector creates its own IN ITS LOOP (inside `_loop()`) and drains it on each tick — state does not live in the
    connector (v2 stateless). Events from other platforms are discarded on drain (no leakage)."""

    _TOPIC = ""

    def __init__(self, platform: str):
        self.platform = platform
        self._sub = bus.subscribe(self._TOPIC)

    def drain(self) -> list[dict]:
        out: list[dict] = []
        q = self._sub.queue
        while True:
            try:
                ev = q.get_nowait()
            except Exception:
                break
            if (ev or {}).get("platform") == self.platform:
                out.append(ev)
        return out

    def close(self) -> None:
        try:
            self._sub.close()
        except Exception:
            pass


class MarkReadInbox(_PlatformInbox):
    """Per-platform subscription to `msg.mark_read`. Replaces `store.take_pending_read(platform)` in the v2 path."""
    _TOPIC = TOPIC_MARK_READ


class ReplyInbox(_PlatformInbox):
    """Per-platform subscription to `msg.reply` (V2-051). The connector drains and SENDS the reply in its app."""
    _TOPIC = TOPIC_REPLY
