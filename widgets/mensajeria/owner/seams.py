#
# owner/seams.py — the small doors the messaging owner talks through: the operator note, the secret scan a
# model-composed text passes before it leaves, the origin of an incoming message, and the outbox bookkeeping
# (settling a send, recording the body it left with).
#
from loguru import logger

from connectors.messaging import store as msgstore


def _note(text: str) -> None:
    """Tell the operator through the brain's inbox. Used for the failures he cannot see any other way — the
    same seam the connectors use for a send that did not go out."""
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


def _scrub(text: str) -> tuple[str, str]:
    """V2-683 — the last door before a MODEL-composed text leaves toward somebody outside. Returns
    `(text, "")` when it is clean and `(text, what)` when it is not, and the caller does not send.

    It FAILS CLOSED, and deliberately does not redact-and-send: a reply's text is dictated by the operator
    and goes to a conversation he is already in, but this one was written by a model for a third party, so a
    secret inside it is either a mistake or an injection, and both are answered by stopping rather than by
    delivering a redacted version he never got to read. `memory/secrets.py` is the same detector the worker
    bridge already runs on anything leaving through `push_channel`."""
    try:
        from memory import secrets as _secrets
        found = _secrets.detect(text or "")
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        logger.warning(f"mensajeria: no pude revisar el texto saliente ({e!r}) — no se envía")
        return (text, "un texto que no he podido revisar")
    if found:
        kinds = sorted({str(getattr(f, "kind", "") or "un secreto") for f in found})
        return (text, ", ".join(kinds))
    return (text, "")


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


def _settle(ref, ok: bool, reason: str = "") -> None:
    """Settle the card's outbox row for the send `ref` (V2-819). Never raises: bookkeeping is not the send."""
    try:
        from .. import sent as _sent
        db = msgstore.load()
        if _sent.outbox_settle(db, ref, ok, reason):
            msgstore.save(db)
    except Exception as e:  # noqa: BLE001
        logger.info(f"mensajeria: outbox row {ref} not settled ({type(e).__name__}: {e})")


def _record_left(ev: dict) -> None:
    """V2-807 T-12 — the body a send of this card LEFT with, on the timeline (`sent.left_event`): what was sent is
    then read from the record, never rebuilt from the conversation that wrote it."""
    from .. import sent as _sent
    rec = _sent.left_event(ev)
    if rec is None:
        return
    try:
        from voice.observer import emit
        emit("widget", "sent", text=rec["text"], extra={"id": "mensajeria", **rec["extra"]})
    except Exception as e:  # noqa: BLE001 — bookkeeping never breaks the owner's loop
        logger.info(f"mensajeria: the sent body was not recorded ({type(e).__name__}: {e})")
