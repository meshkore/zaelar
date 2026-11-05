#
# outbound.py — what zaelar SENDS through the bridge: one message as the app sends it, a dictated reply and its
# echo, the JID a phone becomes, and a first message to somebody who has not written.
#
import asyncio
import time

import aiohttp
from loguru import logger

from connectors.messaging import ingest, store
from connectors.whatsapp import client
from connectors.whatsapp import service as _svc

PLATFORM = _svc.PLATFORM

# ── a send that did not leave: the real cause, and ONE retry when the link comes back (V2-854 F4) ──────────────
# Measured on his engine (2026-11-05 15:46): the bridge's socket dropped mid-send (`Connection Closed` 428, then a
# 408 close), the request timed out with an EMPTY exception, and the line told him «that number may not have
# WhatsApp» — a cause nothing had measured. WhatsApp reconnected twelve seconds later and nothing retried. Now the
# cause is the failure's own (the bridge's sentence, or the exception's class when it has none), a LINK failure —
# the bridge never answered, answered «not connected», or says it is not connected right after — is held and sent
# once more on the next reconnect, and before that second try the card's own record of what LEFT decides: a message
# already in that conversation is never sent twice.

#: A held send older than this is not retried any more (a question sent hours late is a different message).
RETRY_WITHIN_S = 600.0
#: How many held sends are kept at most.
HELD_MAX = 20
#: How long after the reconnect the retry waits: the phone's echo of a send that DID leave needs an inbound pass
#: and the card's owner to land in the sent record before that record can say «it left».
SETTLE_S = 8.0


def cause_of(e: BaseException) -> tuple[bool, str]:
    """(link, why): `link` when the failure is the CONNECTION's — the bridge did not answer (timed out, refused,
    dropped) or answered that it is not connected (503). `why` is the real cause, never empty."""
    if isinstance(e, client.BridgeError):
        return e.status == 503, (e.error or str(e)).strip()[:200]
    why = str(e).strip() or type(e).__name__
    return isinstance(e, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError, aiohttp.ClientError)), why[:200]


def _line(key: str, **kw) -> str:
    try:
        from i18n import langs
        tpl = str(getattr(langs.current_language(), key, "") or "")
        return tpl.format(platform="WhatsApp", **kw) if tpl else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"WhatsApp: no line {key} — {e!r}")
        return ""


async def _failed(r: dict, chat_id: str, e: BaseException, kind: str) -> None:
    """A `kind` («send» | «reply») to `chat_id` raised `e`: the card hears why, he hears the real cause once, and a
    LINK failure on a first try is held for the next reconnect."""
    link, why = cause_of(e)
    if not link:
        try:   # the bridge answered an error: is it still connected? A link that dropped under it is the link's.
            link = ((await client.health()) or {}).get("status") != "connected"
        except Exception:  # noqa: BLE001 — no health answer IS the link down
            link = True
    logger.warning(f"WhatsApp: the {kind} to {chat_id} did not leave ({'link' if link else 'refused'}): {why}")
    ingest.publish_send_failed({**r, "platform": PLATFORM}, why)
    name = r.get("name") or r.get("to") or chat_id
    if link and not r.get("_retry"):
        _svc._held.append({"order": {k: v for k, v in r.items() if k != "_retry"}, "kind": kind, "chatId": chat_id,
                           "at": time.time()})
        del _svc._held[:-HELD_MAX]
        _svc._note(_line("send_link_down", name=name, cause=why))
    else:
        _svc._note(_line("send_refused", name=name, cause=why))


def _left(chat_id: str, text: str, files: list, since: float) -> bool:
    """Did a message with this body reach this conversation since `since`? The card's own sent record decides
    (`widgets/mensajeria/sent.rows`, the record a verifier reads) — the phone's echo of a send that did leave lands
    there even when the bridge's answer never came back."""
    try:
        from widgets.mensajeria import sent as _sent
        body = " ".join(str(text or "").split())
        for row in _sent.rows(store.load()):
            if (row.get("platform") == PLATFORM and str(row.get("chatId")) == str(chat_id) and not row.get("queued")
                    and float(row.get("ts") or 0) >= since - 60.0
                    and (" ".join(str(row.get("body") or "").split()) == body if body else bool(files))):
                return True
    except Exception as e:  # noqa: BLE001 — an unreadable record is no proof it did NOT leave: never resend blind
        logger.warning(f"WhatsApp: the sent record is unreadable, the held send is not retried ({e!r})")
        return True
    return False


async def retry_held(reconnected_at: float) -> None:
    """The connector is connected again: every send held BEFORE that reconnect is tried once — unless the sent record
    shows it left after all. A held send past `RETRY_WITHIN_S` is dropped and said. Never raises."""
    now, keep = time.time(), []
    for h in list(_svc._held):
        order, chat_id = h["order"], h["chatId"]
        name = order.get("name") or order.get("to") or chat_id
        if now - h["at"] > RETRY_WITHIN_S:
            logger.info(f"WhatsApp: a held {h['kind']} to {chat_id} expired unretried")
            _svc._note(_line("send_not_retried", name=name))
            continue
        if not reconnected_at or h["at"] >= reconnected_at or now - reconnected_at < SETTLE_S:
            keep.append(h)               # down, failed after the last reconnect, or the record is still settling
            continue
        try:
            if _left(chat_id, order.get("text") or "", order.get("attachments") or [], h["at"]):
                logger.info(f"WhatsApp: the held {h['kind']} to {chat_id} had left after all — not sent again")
                _svc._note(_line("send_retried_ok", name=name))
                continue
            retry = {**order, "_retry": True}
            ok = await (_reply_one(retry) if h["kind"] == "reply" else _send_one(retry))
            if ok:
                _svc._note(_line("send_retried_ok", name=name))
        except Exception as e:  # noqa: BLE001 — one held send never stops the others
            logger.warning(f"WhatsApp: the retry of a held {h['kind']} to {chat_id} failed: {e!r}")
    _svc._held[:] = keep


async def _send(chat_id: str, text: str, files: list[str], reply_to: str | None = None) -> dict:
    """One message as the native app sends it: the files, the text as the FIRST file's caption when that file
    can carry one (a voice note cannot), otherwise the text on its own. Returns the last send's answer."""
    files = store.sendable(files)
    if not files:
        return await client.send_message(chat_id, text, reply_to=reply_to) or {}
    res: dict = {}
    caption_used = False
    for i, path in enumerate(files):
        cap = text if (i == 0 and text and store.kind_of(path) not in ("ptt", "audio")) else ""
        caption_used = caption_used or bool(cap)
        res = await client.send_media(chat_id, path, caption=cap) or {}
    if text and not caption_used:
        res = await client.send_message(chat_id, text, reply_to=reply_to) or res
    return res


async def _drain_replies() -> None:
    """Drain dictated replies (V2-521 — the email connector had this since V2-051; WhatsApp only ever read).
    The widget's reply action already enqueued mark-read for the original, so this only SENDS. A failure is
    TOLD to the operator through brain_notes and not requeued: a bad send retried forever is worse than one
    honest "I couldn't send it."""
    if not ingest.v2_enabled() or _svc._reply_inbox is None:
        return
    for r in _svc._reply_inbox.drain():
        await _reply_one(r)


async def _reply_one(r: dict) -> bool:
    """One dictated reply: sent and echoed (True), or its failure handled by `_failed` (False)."""
    chat_id = str(r.get("chatId") or r.get("to") or "").strip()
    text = (r.get("text") or "").strip()
    files = r.get("attachments") or []
    if not chat_id or not (text or files):
        return False
    try:
        res = await _svc._send(chat_id, text, files, reply_to=r.get("messageId") or None)
    except Exception as e:  # noqa: BLE001
        # V2-819 — and the card that sent it hears it too: its row keeps his text and says why.
        await _failed(r, chat_id, e, "reply")
        return False
    logger.info(f"WhatsApp: respuesta enviada a {chat_id}")
    # V2-847 — no note tells the model this send happened: the echo below settles the request's row, and the
    # mouth says the verdict (`nucleo/turn/reply.py`). A note that ordered «confirm it» named whatever `to` held
    # and was spoken as the person he meant — one door for what an act did, never a second one.
    _svc._echo_sent(r, chat_id, text, files, res)
    return True


def _echo_sent(r: dict, chat_id: str, text: str, files: list, res: dict | None) -> None:
    """V2-819 — a reply that LEFT joins its conversation now, under the id WhatsApp gave it (the phone's own echo
    of the same message then lands on the same row), and carries the order's `ref` so the card that sent it
    knows. Outside the send's try on purpose: failing to RECORD a message is not failing to SEND it."""
    try:
        import time as _t
        mid = (res or {}).get("messageId") or f"sent:{_t.time():.0f}"
        _svc._published.add(mid)
        ingest.publish_msg_out(PLATFORM, {
            "chatId": chat_id, "messageId": mid, "ref": r.get("ref") or "", "from": "", "body": text,
            "timestamp": _t.time(), **({"retried": True} if r.get("_retry") else {}),
            **({"media": store.media_refs(store.sendable(files)),
                "mediaType": store.kind_of(files[0])} if files else {})})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WhatsApp: enviado, pero no pude registrar la conversación: {e}")


def _jid(handle: str) -> str:
    """The conversation id WhatsApp addresses a person by, from whatever we hold. A JID is already one; a
    phone becomes `<digits>@s.whatsapp.net`, which is exactly what the bridge's own chat ids look like — so a
    conversation opened this way is keyed the same as one that arrived on its own, and the thread does not
    split in two. Punctuation and spaces are dropped because a stored number is written for a human."""
    h = str(handle or "").strip()
    if "@" in h:
        return h
    digits = "".join(ch for ch in h if ch.isdigit())
    return f"{digits}@s.whatsapp.net" if digits else ""


async def _drain_sends() -> None:
    """Drain orders that OPEN a conversation (V2-683): a first message to somebody who has not written.

    WhatsApp has no «resolve this person» step — a number IS the address — so the only translation is the JID
    above. What the bridge cannot tell us is whether that number has WhatsApp at all: it answers with an
    error, and that error is reported once and never retried, which is the honest half of the asymmetry
    `widgets/directory.py` documents (a phone is offered for WhatsApp only when the operator NAMED it)."""
    if not ingest.v2_enabled() or _svc._send_inbox is None:
        return
    for r in _svc._send_inbox.drain():
        await _send_one(r)


async def _send_one(r: dict) -> bool:
    """One first message: sent and echoed (True), or its failure handled by `_failed` (False). The cause a failure
    carries is its own — a number with no WhatsApp is never inferred from a send that did not leave."""
    chat_id = str(r.get("chatId") or "").strip() or _jid(r.get("to"))
    text = (r.get("text") or "").strip()
    files = r.get("attachments") or []
    if not chat_id or not (text or files):
        return False
    try:
        res = await _svc._send(chat_id, text, files)
    except Exception as e:  # noqa: BLE001
        await _failed(r, chat_id, e, "send")
        return False
    # SENT — the echo sits outside the try on purpose (see the Telegram drain): a failure to RECORD the
    # message must never be reported as a failure to SEND it.
    logger.info(f"WhatsApp: mensaje enviado a {chat_id} (ref {r.get('ref')})")
    try:
        import time as _t
        ingest.publish_msg_out(PLATFORM, {
            "chatId": chat_id, "messageId": (res or {}).get("messageId") or f"sent:{_t.time():.0f}",
            "ref": r.get("ref"), "from": "", "body": text, "timestamp": _t.time(),
            "contactId": r.get("contactId") or "",
            "chatName": r.get("name") or "",
            **({"retried": True} if r.get("_retry") else {}),
            **({"media": store.media_refs(store.sendable(files)),
                "mediaType": store.kind_of(files[0])} if files else {})})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WhatsApp: enviado, pero no pude registrar la conversación: {e}")
    return True
