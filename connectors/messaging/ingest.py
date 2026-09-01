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
TOPIC_ARCHIVE = "msg.archive"      # V2-543: widget asks to ARCHIVE in the real mailbox (email today)
TOPIC_TRASH = "msg.trash"          # V2-543: widget asks to DELETE in the real mailbox (email today)
# V2-546 — the three signals that make the widget FOLLOW the real app instead of drifting from it. Until these
# existed every connector was inbound-only and read state travelled one way (widget → app), so a chat the
# operator had answered on his phone kept sitting here looking pending.
TOPIC_MSG_OUT = "connector.msg_out"    # the OPERATOR wrote, in his own app: joins the conversation, not the inbox
TOPIC_READ = "connector.read"          # the operator read this chat elsewhere: a watermark, not a list
TOPIC_HISTORY_ASK = "msg.history"      # widget asks a connector for OLDER messages of one chat
TOPIC_HISTORY = "connector.history"    # the connector answers with them


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


def publish_archive(key: dict) -> None:
    """Widget asks to ARCHIVE in the real app (V2-543): {platform, chatId, messageId, senderId}. That platform's
    connector (email today) drains it and moves the mail out of the inbox for real."""
    try:
        bus.emit_sync(TOPIC_ARCHIVE, dict(key or {}))
    except Exception:
        pass


def publish_trash(key: dict) -> None:
    """Widget asks to DELETE in the real app (V2-543). Irreversible on the platform side — the widget's action
    is confirm-gated before it ever reaches here."""
    try:
        bus.emit_sync(TOPIC_TRASH, dict(key or {}))
    except Exception:
        pass


class MarkReadInbox(_PlatformInbox):
    """Per-platform subscription to `msg.mark_read`. Replaces `store.take_pending_read(platform)` in the v2 path."""
    _TOPIC = TOPIC_MARK_READ


class ArchiveInbox(_PlatformInbox):
    """Per-platform subscription to `msg.archive` (V2-543)."""
    _TOPIC = TOPIC_ARCHIVE


class TrashInbox(_PlatformInbox):
    """Per-platform subscription to `msg.trash` (V2-543)."""
    _TOPIC = TOPIC_TRASH


class ReplyInbox(_PlatformInbox):
    """Per-platform subscription to `msg.reply` (V2-051). The connector drains and SENDS the reply in its app."""
    _TOPIC = TOPIC_REPLY


class HistoryAskInbox(_PlatformInbox):
    """Per-platform subscription to `msg.history` (V2-546): the widget asking for OLDER messages of one chat."""
    _TOPIC = TOPIC_HISTORY_ASK


# ── V2-546 publishers ───────────────────────────────────────────────────────
def publish_msg_out(platform: str, msg: dict) -> None:
    """A message the OPERATOR sent from his own app. Same normalized shape as an inbound one; the widget appends
    it to the conversation and treats the chat as seen. It is deliberately NOT `connector.msg`: that topic feeds
    triage and notification, and being told about one's own message is neither news nor a decision."""
    try:
        bus.emit_sync(TOPIC_MSG_OUT, {"platform": platform, **(msg or {})})
    except Exception:
        pass


def publish_read(platform: str, chat_id, upto_ts: float | None = None, ids=None) -> None:
    """The operator read this chat somewhere else. `upto_ts` is a WATERMARK (the shape every platform's read
    receipt actually has); `ids` is for the one source that can only speak per-message (IMAP flags)."""
    try:
        bus.emit_sync(TOPIC_READ, {"platform": platform, "chatId": chat_id,
                                   "uptoTs": upto_ts, "ids": list(ids or []) or None})
    except Exception:
        pass


def publish_history_ask(order: dict) -> None:
    """Widget asks a connector for older messages: {platform, chatId, beforeTs, beforeId, limit}."""
    try:
        bus.emit_sync(TOPIC_HISTORY_ASK, dict(order or {}))
    except Exception:
        pass


def publish_history(platform: str, chat_id, msgs: list[dict], complete: bool = False,
                    error: str = "") -> None:
    """A connector answers with older messages. `complete` = it proved there is nothing before these, so the
    widget stops offering the button. `error` travels too: a request that could not be served has to SAY so —
    a silent no-op is indistinguishable from a chat with no history."""
    try:
        bus.emit_sync(TOPIC_HISTORY, {"platform": platform, "chatId": chat_id,
                                      "msgs": list(msgs or []), "complete": bool(complete),
                                      "error": error or ""})
    except Exception:
        pass
