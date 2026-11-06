"""nucleo/errands/mandate.py — what an errand may SEND, read through the one consent door (V2-805).

An errand answers a third party under a MANDATE he granted with the order that opened it («contacta con X y
organiza…»): `mandate.may` names what it may do (`message`, `schedule`) and `mandate.channels` where. Before V2-805
the wake sent every reply the model wrote without reading either the mandate's `message` grant or his rules, so
«pregúntame antes de mandar un WhatsApp» never reached an errand's WhatsApp, and an errand whose mandate did not
grant messaging sent anyway.

Two halves, kept apart on purpose:

  · **The mandate is a CONSEQUENCE bound** (CRIT-E6): it is the operator's grant for THIS conversation, and a
    reply it does not cover never leaves on a class default — it is held for his word, like `book.may_schedule`
    holds a slot it may not write.
  · **Inside the mandate, the shared rule decides** (`consent.decide_act`, class `messaging.send_new`, the
    thread's channel): the mandate travels as `his_yes`, so the class default adds no question to a conversation
    he ordered, and his standing «ask»/«never» for that channel still stop it — the same answer an email or a
    cluster message gets.

Held = a draft row of the mail card for that conversation (`widgets/mensajeria/drafts.py`), the SAME row his
«send it» resolves by voice, by chat or by the card's own button (`send_draft`, CRIT-C9).
"""
from __future__ import annotations

from loguru import logger

CLASS = "messaging.send_new"

#: THE vocabulary of a grant (V2-857 P0-3): what an errand, a stream or a standing rule may do without asking — one
#: list, declared once with every other event type (`nucleo/events/vocabulary.GRANTS`), which the rule reader asks
#: the model for (`rules/subscriptions`) and every exit reads. A rule's `may: ["reply"]` used to be a word no exit knew
#: (`exit_gate.under_mandate` read `message`), so «when X writes, answer her» asked him at every item and the rule was
#: dead. Each grant: its name, what it lets do, and the older words rows written before the vocabulary was one used.
from nucleo.events.vocabulary import GRANTS as MAY  # noqa: E402
from nucleo.events.vocabulary import grants_of as acts  # noqa: E402,F401 — `may` in THE vocabulary, unknown words dropped


def covers(errand: dict, platform: str) -> bool:
    """Does the errand's mandate grant a message on this channel? Unreadable → no: a message to a person is not
    the direction to fail open in (the same choice `book.may_schedule` makes for his calendar)."""
    mandate = errand.get("mandate") if isinstance(errand, dict) else None
    if not isinstance(mandate, dict):
        return False
    if "message" not in acts(mandate.get("may")):
        return False
    channels = [str(c).strip().lower() for c in (mandate.get("channels") or []) if str(c).strip()]
    return not channels or str(platform or "").strip().lower() in channels


def verdict(errand: dict, platform: str) -> dict:
    """The one consent rule for this reply. Outside the mandate it is a question, whatever the class default."""
    from nucleo import consent
    if not covers(errand, platform):
        return {"verdict": consent.ASK_CONSENT, "why": "el mandato del encargo no cubre este mensaje",
                "level": "sensitive", "needs": [], "candidates": [], "n": 1}
    return consent.decide_act(CLASS, channel=platform, his_yes=True)


def deliver(errand: dict, platform: str, chat_id: str, text: str, party: str, send, tell) -> bool:
    """Send under the mandate when the shared rule says so; otherwise hold it as a draft row (asked) or drop it
    (his «never»), and tell him. `send(...)` and `tell(text)` are the wake's own doors. True = it went out."""
    from nucleo import consent
    v = verdict(errand, platform)
    if not consent.asks(v):
        return send(errand, platform, chat_id, text, party)
    topic = str(errand.get("objective") or "")[:80]
    if v.get("verdict") == consent.REFUSE:
        tell(f"[SISTEMA] Sobre «{topic}»: {party or 'la otra persona'} espera respuesta y su regla prohíbe mandarla "
             f"por {platform}. No se ha enviado nada. Díselo al operador.")
        return False
    if hold(platform, chat_id, text, party):
        tell(f"[SISTEMA] Sobre «{topic}»: he dejado en borrador la respuesta para {party or chat_id} "
             f"({v.get('why') or 'su regla'}): «{text[:160]}». Pregúntale al operador si la mando.")
    return False


def hold(platform: str, chat_id: str, text: str, party: str) -> bool:
    """The reply as a draft row of the mail card for this conversation — what his «send it» sends."""
    try:
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import drafts
        db = msgstore.load()
        drafts.write(db, {"platform": platform, "to": chat_id, "chatId": chat_id, "name": party,
                          "contactId": "", "new": True}, text, False)
        msgstore.save(db)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: could not hold the reply for {chat_id} as a draft ({e!r}) — nothing was sent")
        return False
