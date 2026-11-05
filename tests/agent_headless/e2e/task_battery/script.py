"""What the operator says in each case, per language, and the steps several cases share (V2-851 §9).

The sentences are product DATA (what a user says), so they are in the case's language; everything else is English.
A domain variant changes ONE thing — the person, the channel, one word of the errand — to prove the class, not the
case. Nothing here reads the reply's wording: the cases read rows, flow events and wall lines.
"""
from __future__ import annotations

import time

from . import seed
from .probe import LIVE_STATES, Probe, Turn

LANGS = ["es", "en"]

#: Who the C1 family writes to: the ambiguous first name, or the second ambiguous pair (domain variant).
WHO = ["ambiguous", "ambiguous2"]

SEND = {"es": "Mándale un mensaje a {who} diciéndole que llego diez minutos tarde",
        "en": "Send {who} a message saying I'll be ten minutes late"}
SEND_OTHER = {"es": "Y escríbele a {who} que mañana no puedo quedar",
              "en": "And text {who} that I can't make it tomorrow"}
#: The answer that picks the FIRST person of the pair (`seed.PEOPLE[lang]["contacts"]` order).
PICK = {"es": "A {full}", "en": "To {full}"}
AMBIGUOUS_ANSWER = {"es": "Al primero", "en": "The first one"}
STATUS = {"es": "¿Cómo va lo de {who}?", "en": "How's the {who} thing going?"}
STOP = {"es": "Para. Cancela esa búsqueda, ya no la necesito.", "en": "Stop. Cancel that search, I don't need it."}

#: C5 — a send to the one unambiguous person, by her preferred channel or (variant) by mail.
SEND_SINGLE = {"es": {"telegram": "Mándale un mensaje a {who} diciéndole que llego a las ocho",
                      "email": "Mándale un correo a {who} diciéndole que llego a las ocho"},
               "en": {"telegram": "Text {who} that I'll be there at eight",
                      "email": "Email {who} that I'll be there at eight"}}
#: C6 — a send the door must refuse: a person with no channel, or a channel she does not have (variant).
REFUSED = {"es": {"no_channel": "Mándale un mensaje a {unreachable} diciéndole que mañana no puedo",
                  "wrong_channel": "Mándale un WhatsApp a {single} diciéndole que mañana no puedo"},
           "en": {"no_channel": "Text {unreachable} that I can't make it tomorrow",
                  "wrong_channel": "Send {single} a WhatsApp saying I can't make it tomorrow"}}

#: Free errands (C8, C11, C12). `hostel` is `hotel` with ONE word changed; `document` is the other playbook.
ERRAND = {
    "es": {"hotel": "Búscame un hotel en Valencia para el próximo fin de semana, de menos de 120 euros la noche",
           "hostel": "Búscame un hostal en Valencia para el próximo fin de semana, de menos de 120 euros la noche",
           "flights": "Busca vuelos de Madrid a Lisboa para el viernes que viene",
           "document": "Escríbeme un documento con un plan de tres días para visitar Lisboa"},
    "en": {"hotel": "Find me a hotel in Boston for next weekend, under 200 dollars a night",
           "hostel": "Find me a hostel in Boston for next weekend, under 200 dollars a night",
           "flights": "Look for flights from New York to Chicago next Friday",
           "document": "Write me a document with a three-day plan to visit Lisbon"},
}
MIXED = {"es": "Hola, ¿qué tal? " + ERRAND["es"]["hotel"], "en": "Hi, how are you? " + ERRAND["en"]["hotel"]}

#: C9 — the standing rule, and the request that makes a worker read the mail and want to answer it.
RULE = {"es": "Cuando me llegue un correo de {addr}, apúntame en la agenda una tarea para pagar la factura.",
        "en": "When an email from {addr} arrives, add a task to my agenda to pay the invoice."}
MAIL = {"es": [("Factura de octubre", "Adjuntamos la factura de octubre: 84,20 EUR. Vence el 15 de noviembre."),
               ("Factura de noviembre", "Adjuntamos la factura de noviembre: 91,10 EUR. Vence el 15 de diciembre.")],
        "en": [("October invoice", "Please find the October invoice attached: $84.20, due November 15."),
               ("November invoice", "Please find the November invoice attached: $91.10, due December 15.")]}
REPLY_TO_MAIL = {"es": "Lee el último correo de {name} y contéstale por correo lo que te parezca bien",
                 "en": "Read the latest email from {name} and reply to it as you see fit"}


def person(lang: str, role: str) -> str:
    """The first name a role is said with (`ambiguous` → «Raquel»)."""
    return seed.PEOPLE[lang][role]


def candidates(lang: str, role: str) -> list[dict]:
    """The seeded contacts a first name matches, in seed order."""
    first = person(lang, role)
    return [c for c in seed.PEOPLE[lang]["contacts"] if c["name"].split()[0] == first]


def chat_of(contact: dict) -> str:
    return str((contact.get("channels") or [{}])[0].get("chatId") or "")


def sent_since(p: Probe, t0: float) -> list[dict]:
    return [o for o in seed.sent(p.eng.workspace) if float(o.get("at") or 0) >= t0]


def visible_rows_since(p: Probe, t0: float) -> list[dict]:
    return [r for r in p.rows_since(t0) if r.get("visible", True)]


def waiting_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("state") == "waiting"]


def ask_ambiguous(p: Probe, lang: str, role: str = "ambiguous", template: dict = SEND) -> tuple[Turn, list[dict]]:
    """Say the send to an ambiguous name and wait for the question it must raise (the worker's, through Flash).
    Returns the turn and the `ask` events seen (empty on an engine that never raises one)."""
    turn = p.say(template[lang].format(who=person(lang, role)))
    asks = p.wait_for_ask(turn.since, turn.t0)
    return turn, asks


def wait_sent(p: Probe, t0: float, chat: str = "", *, timeout: float = 150.0) -> list[dict]:
    """The loopback orders since `t0` (to `chat` when given), waiting while something born since `t0` is alive."""
    deadline = time.time() + timeout
    grace = time.time() + 8.0
    while True:
        got = [o for o in sent_since(p, t0) if not chat or str(o.get("chatId")) == chat]
        if got or time.time() > deadline:
            return got
        if time.time() > grace and not [r for r in p.rows_since(t0) if r.get("state") in LIVE_STATES]:
            # nothing left alive that could still send; one last look after the owner's flush beat
            time.sleep(4.0)
            return [o for o in sent_since(p, t0) if not chat or str(o.get("chatId")) == chat]
        time.sleep(3.0)


def wait_worker(p: Probe, since: int, *, timeout: float = 200.0) -> dict | None:
    """The first `worker_start` after `since` (the memory envelope may hold a worker up to 60 s before it)."""
    found = p.wait_for(lambda: p.worker_starts_since(since), timeout=timeout, every=3.0) or []
    return found[0] if found else None
