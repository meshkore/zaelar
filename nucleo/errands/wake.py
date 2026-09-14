"""nucleo/errands/wake.py — ONE move of an errand, when the world asks for it (V2-683).

An errand wakes for three reasons: somebody answered on a conversation it owns, its own clock said so, or
the operator asked. Whatever the reason, the move is the same and it is bounded: read the dossier, ask ONE
model turn with no tools, and let the ENGINE execute what came back — inside the mandate and nothing else.

## Why the engine executes and the model does not

The party's words reach the model. If the model held tools, a stranger's sentence would be one
hallucination away from a calendar write or a message to somebody else. So the model returns a decision
and this module decides what of it is allowed: a message goes ONLY to the conversation the errand already
owns, and anything else is a note to the operator. That is the whole security argument, and it is
structural — there is no tool to misuse.

## Shadow

`errands.shadow` (genesis, default TRUE) runs everything except the sending: the decision is made and
LOGGED as `would_say`. The operator flips it once he has read a few of those. Autonomy that writes to real
people is not something to hand over on the strength of a green test suite.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: The model is off-voice here, but a tier can be slow; without a cap one wake would hold the loop's beat.
TIMEOUT_S = 60.0
#: How much of the conversation travels. Enough to answer; never the whole history (it rides a prompt).
MAX_MSGS = 12
#: Nothing is woken more often than this, whatever arrives — a burst of five messages is ONE move.
MIN_GAP_S = 20.0
#: Room for the decision even when the model deliberates anyway (see `_ask_model`).
MAX_TOKENS = 1200

_last_wake: dict[str, float] = {}


def shadow() -> bool:
    """TRUE = decide and log, send nothing. Read per use (the `style_policy` shape), so the operator can
    turn it off without a restart. It FAILS CLOSED: an unreadable setting means shadow, because the failure
    of staying quiet is a message he has to send by hand, and the other failure is a message to a stranger
    that nobody authorised."""
    try:
        from .playbooks import settings
        return bool(settings().get("shadow", True))
    except Exception:
        return True


def _thread_messages(platform: str, chat_id) -> list[dict]:
    try:
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import thread as _thread
        db = msgstore.load()
        th = (db.get("threads") or {}).get(_thread.key(platform, chat_id)) or {}
        return list(th.get("msgs") or [])[-MAX_MSGS:]
    except Exception:
        return []


def _party_name(platform: str, chat_id) -> str:
    """Who this is, best first: the operator's own directory, then the name the CONVERSATION carries.

    The fallback matters more than it looks. Without it the dossier said «PERSONA con la que hablas:
    telegram» on the first live run — the platform standing in for a person, which is what the caller's
    `party or platform` was already doing one level up. The thread knows the name the connector delivered
    it under, and a reply written to «telegram» reads like a reply written to nobody.
    """
    try:
        from widgets import directory
        c = directory.find_by_channel(platform, chat_id)
        name = str((c or {}).get("name") or "")
        if name:
            return name
    except Exception:
        pass
    try:
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import thread as _thread
        th = (msgstore.load().get("threads") or {}).get(_thread.key(platform, chat_id)) or {}
        return str(th.get("name") or "")
    except Exception:
        return ""


def _now_line() -> str:
    return ("AHORA son las " + time.strftime("%H:%M") + " del " + time.strftime("%A %d/%m/%Y") +
            ". No inventes otra fecha ni otra hora.")


async def _ask_model(system: str, dossier: str, *, max_tokens: int = MAX_TOKENS) -> str:
    """⚠️ `no_thinking`, and a budget that is not the deliberation's.

    Measured on the first live run (2026-09-13): the turn brain is `deepseek-v4-pro`, a REASONER, and this
    call asked it for 700 tokens — it spent `reasoning_tokens: 700` of 700 deliberating, came back with
    `finish_reason: length` and `content: ''`, and the errand treated that empty string as an unreadable
    answer and said nothing to a person who was waiting. The V2-658 class exactly, one layer over. So: the
    caller wants the ANSWER and says so (the direct endpoint obeys it; the broker reasons anyway), and the
    budget leaves room for the JSON even when it does.
    """
    from nucleo.flash.fast_client import FastClient
    from nucleo.flash.model_spec import spec_from_config
    return await asyncio.wait_for(
        FastClient().complete([{"role": "system", "content": system},
                               {"role": "user", "content": dossier}],
                              spec=spec_from_config(), max_tokens=max_tokens, tools=None,
                              no_thinking=True),
        timeout=TIMEOUT_S)


def _identity() -> tuple[str, str, str]:
    """Who we are, who he is, and his language — the ONLY three facts about the operator that may cross."""
    name, op, lang = "zaelar", "", "español"
    try:
        from memory import api as memory
        st = memory.state() or {}
        name = str(st.get("assistant_name") or "zaelar")
        op = str(st.get("operator_name") or "")
    except Exception:
        pass
    try:
        from i18n import langs as _lg
        lang = _lg.current_language().native
    except Exception:
        pass
    return name, op, lang


async def wake(errand: dict, *, reason: str = "inbound", inbound_id: str = "",
               now: float | None = None) -> dict:
    """Move this errand once. Returns what was decided (and, out of shadow, what was done)."""
    from . import close, note_wake, threads, update
    now = time.time() if now is None else now
    eid = str(errand.get("id") or "")
    if not eid:
        return {"ok": False, "why": "sin id"}
    if now - _last_wake.get(eid, 0.0) < MIN_GAP_S:
        return {"ok": False, "why": "coalesced"}
    _last_wake[eid] = now

    # ⏻ — a stopped agent spends nothing and says nothing. Postponed, never lost: the next beat after he
    # starts it again finds the same errand exactly where it was (`_fire_due`'s rule, V2-092).
    try:
        from nucleo import runstate
        if runstate.blocks_new_work():
            return {"ok": False, "why": "parado"}
    except Exception:
        return {"ok": False, "why": "no pude leer el interruptor"}

    th = (threads(eid) or [{}])[0]
    platform, chat_id = str(th.get("platform") or ""), str(th.get("chat_id") or "")
    party = _party_name(platform, chat_id)
    msgs = _thread_messages(platform, chat_id)

    # The idempotency mark is written BEFORE anything is sent. Afterwards, a crash in between is a message
    # delivered twice — and to a person, which is not a retry, it is an embarrassment.
    if inbound_id:
        note_wake(eid, inbound_id)
    else:
        note_wake(eid)

    name, op, lang = _identity()
    brief, busy = "", ""
    try:
        from .playbooks import brief_for, free_slots_line
        brief = brief_for(errand.get("kind") or "")
        busy = free_slots_line(errand, now)
    except Exception:
        pass
    # V2-692d — what the model may PROMISE is read from the world, per wake: he can link his calendar
    # between one message and the next, and a promise made on a stale answer is paid by a stranger.
    from . import book as _book
    can_link = _book.can_mint_link()
    system = _build_system(name, op, lang, can_link=can_link)
    dossier = _build_dossier(errand, party=party or platform, messages=msgs, brief=brief,
                             now_line=_now_line(), busy=busy)
    try:
        raw = await _ask_model(system, dossier)
        if not raw.strip():
            # NOTHING came back — not a decision, an empty turn. One retry with a wider budget, because the
            # commonest cause is a reasoner that spent the whole of it deliberating, and the cost of giving
            # up here is a person left unanswered. Bounded by construction: exactly one extra call.
            logger.info(f"errands: el modelo no dijo nada en {eid} — lo pido otra vez con más margen")
            raw = await _ask_model(system, dossier, max_tokens=MAX_TOKENS * 2)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: el turno con el tercero falló ({e!r}) — el encargo se queda como estaba")
        return {"ok": False, "why": "modelo"}

    from . import party as _party
    decision = _party.parse(raw)
    if decision is None:
        # Loud here, silent toward the person: a reply we cannot read must never become half an action.
        # And the OPERATOR is told, because this is the shape he must never discover by himself: somebody
        # answered, the errand could not answer back, and from outside that is indistinguishable from a
        # gestión still quietly in flight.
        logger.warning(f"errands: respuesta ilegible en {eid} — no se hace nada ({raw[:120]!r})")
        _emit_decision(errand, {"say": "", "reason": "respuesta ilegible"}, reason, sent=False)
        _tell_operator(
            f"[SISTEMA] Te han contestado sobre «{str(errand.get('objective') or '')[:80]}» y no he sabido "
            f"qué responder. Díselo al operador y pregúntale si contesta él.")
        return {"ok": False, "why": "ilegible"}

    say = decision.get("say") or ""
    ask_op = decision.get("ask_operator") or ""
    state = decision.get("state") or ""

    # ⚠️ THE BOOKING HAPPENS BEFORE THE REPLY, and the order is the feature (V2-692). The model has just
    # been told it may promise the link; the engine mints it by CREATING the event, so composing the
    # message first would send a promise whose object does not exist yet and leave the link for a second
    # message nobody triggers. A failure here writes nothing and says nothing new: the reply still goes,
    # the errand stays where it was, and the next inbound tries again — losing an agreement the other
    # person already gave is the one outcome worth avoiding.
    booked = {}
    if state == "agreed":
        booked = _book.book(errand, decision, party or platform)
        if booked.get("ok"):
            say = _with_link(say, str(booked.get("link") or ""))
        elif booked.get("why"):
            logger.info(f"errands: {eid} acordó y no pude apuntarlo ({booked['why']})")

    sent = False
    if say and platform and chat_id and not shadow():
        sent = _send(errand, platform, chat_id, say, party)
    _emit_decision(errand, decision, reason, sent=sent, booked=booked)

    if state and state != errand.get("state"):
        update(eid, state=state)
    if ask_op:
        _tell_operator(f"[SISTEMA] Sobre «{str(errand.get('objective') or '')[:80]}»: {ask_op} "
                       f"Pregúntaselo al operador.")
    # The one thing the errand cannot solve by itself and he can, in one click. Said ONCE per errand, and
    # only when the meeting really was written and really has no link — not every time the calendar is
    # disconnected, which would be a nag about a connector he may not want.
    if booked.get("ok") and not booked.get("link") and not can_link:
        _tell_operator(
            f"[SISTEMA] He cerrado «{str(errand.get('objective') or '')[:70]}» y he apuntado la cita, pero "
            f"NO he podido crear el enlace de videollamada: su Google Calendar no está conectado. Díselo al "
            f"operador en una frase y que lo conecte si quiere que el enlace salga solo.")
    if state in ("blocked", "abandoned"):
        close(eid, state, decision.get("reason") or "")
    return {"ok": True, "say": say, "sent": sent, "state": state, "shadow": shadow(),
            "booked": bool(booked.get("ok"))}


def _with_link(say: str, link: str) -> str:
    """Append the conference link the ENGINE minted, on its own line and with no prose around it.

    No sentence of ours travels with it: the reply is written in the PARTY's language (which may be neither
    of the two this repo ships), so a Castilian «Aquí tienes el enlace» glued onto an answer in German is
    the V2-676 defect aimed outward, at somebody who is not even our operator. A bare URL reads correctly
    in every language there is. An empty `say` gets nothing: a link with no message is a stranger receiving
    a naked URL.
    """
    if not link or not say.strip() or link in say:
        return say
    return say.rstrip() + "\n" + link


def _send(errand: dict, platform: str, chat_id: str, text: str, party: str) -> bool:
    """Put the reply in the SAME outbound queue a human-dictated one uses (`msg.send`), on the conversation
    this errand already owns. It can go nowhere else: the address is the binding, not something the model
    chose."""
    try:
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import outbound
        db = msgstore.load()
        outbound.enqueue(db, {"platform": platform, "to": chat_id, "chatId": chat_id, "name": party,
                              "contactId": ""}, text, ref=f"{errand.get('id')}:{int(time.time())}")
        msgstore.save(db)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: no pude encolar la respuesta de {errand.get('id')}: {e!r}")
        return False


def _tell_operator(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


def _emit_decision(errand: dict, decision: dict, reason: str, *, sent: bool,
                   booked: dict | None = None) -> None:
    """What it decided, always — in shadow this row IS the feature: it is what the operator reads before
    deciding whether to let it speak."""
    try:
        from voice.observer import emit
        say = str(decision.get("say") or "")
        emit("errand", ("💬 encargo: respuesta enviada" if sent else
                        "🌑 encargo (sombra): lo que diría" if say else "🤔 encargo: sin nada que decir"),
             text=say[:160], role="system",
             extra={"errand": errand.get("id"), "state": decision.get("state") or errand.get("state"),
                    "reason": decision.get("reason") or "", "wake": reason, "sent": sent,
                    "shadow": shadow(),
                    **({"booked": bool((booked or {}).get("ok")),
                        "meet": bool((booked or {}).get("link"))} if booked else {})})
    except Exception:
        pass


def _build_system(name: str, op: str, lang: str, can_link: bool = False) -> str:
    from . import party as _party
    return _party.build_system(name, op, lang, can_link=can_link)


def _build_dossier(errand, **kw) -> str:
    from . import party as _party
    return _party.build_dossier(errand, **kw)
