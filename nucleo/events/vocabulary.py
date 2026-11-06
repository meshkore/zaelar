"""nucleo/events/vocabulary.py — THE vocabulary of events: what arrives and what leaves, declared once (V2-857 phase 1).

The architecture audit of 2026-11-05 found five tables for «what leaves and what it may do»: the event topics
(inbound only), the consent classes (genesis plus a few born in code), the mandate's `may`, the manifest's `effects`
and the consequence doors. Each new act needed a row in each — or got one in some, and the others went blind: a
class with no default had no scope a rule could name (`errand.mesh_serve`: «no me preguntes para los encargos a la
red» landed at `global`), and a manifest that declared a leaving class but forgot `external.send` had an exit no door
read.

An event TYPE is `<family>.<act>`, declared here once with its direction. An INSTANCE adds what only the moment knows:
its CHANNEL (`<family>.<act>@<channel>`, `consent.act_key`; the rules scope `<family>/<channel>/<act>`) and its
SUBJECT (the person or the item it is about — the rules cascade's `subject:` rung). From this table are DERIVED:

  · the consent key of a leaving act and its default level (`consent.decide_act` with no `level`);
  · the scopes a spoken rule may name (`rules.vocabulary.classes`): every leaving type is a place his rule reaches;
  · the topics a rule may subscribe to (`rules.subscriptions.TOPICS`): the types that ARRIVE;
  · the grants a mandate may hold (`nucleo.errands.mandate.MAY` is `GRANTS`), each leaving type naming the grant that
    covers it, so a rule's «may reply» and the exit door's «is a message under mandate» are one word;
  · the effect a manifest action carries by its class (`widgets.effects.of`): an action of class `messaging.send_new`
    LEAVES whether or not its manifest repeats `external.send`.

Deliberately NOT derived from here: `nucleo.consequence.DOORS`. Those are the TURN's funnels for a dry run — speech,
memory, the worker's own doors — a wider set than the world, and a dry turn must close all of them. A leaving event's
outcome is recorded on one of them (`mesh.serve` today); the door stays declared with its funnel.

Nothing here reads words. A type is named by the code that declares the act, and this module only says what the
name means to each reader.
"""
from __future__ import annotations

from typing import NamedTuple

IN = "in"          # arrives from the world without a turn; a rule may subscribe to it
OUT = "out"        # leaves to the world; the one consent rule decides it (`consent.decide_act`)
TASK = "task"      # the engine's own: a task of his ended or asks; routed, never subscribed by a rule

# ── the names, so the producers and this table spell them once ───────────────────────────────────────────────
CONNECTOR_MSG = "connector.msg"
MAIL_IN = "mail.in"
CLUSTER_MSG = "cluster.msg"
CRON_DUE = "cron.due"
WORKER_DONE = "worker.done"
WORKER_ASK = "worker.ask"


class Grant(NamedTuple):
    """What a mandate (an errand's, a stream's, a standing rule's) lets a worker do without asking."""
    name: str
    what: str
    older: tuple          # the words rows written before the vocabulary was one used for it


#: THE grants (V2-857 P0-3 moved them here from `nucleo/errands/mandate.MAY`, which now re-exports this tuple).
GRANTS = (Grant("message", "send, reply to or forward a message to someone", ("reply", "forward", "send")),
          Grant("schedule", "put something on his agenda", ("agenda", "book")),
          Grant("note", "write a note or a reminder for him", ()))


class EventType(NamedTuple):
    name: str             # <family>.<act>
    direction: str        # IN · OUT · TASK
    what: str             # one line: for the rule reader's prompt, for the scopes a rule may name, for him
    grant: str = ""       # OUT: the grant that covers it; "" when none does (money, an account, a login)
    level: str = ""       # OUT: its default sensitivity when the caller measured none (`consent.LEVELS`)
    effect: str = ""      # OUT: what an action of this class carries (`widgets.effects`: external.send, data.write)


TYPES: tuple[EventType, ...] = (
    # ── arrives ──
    EventType(MAIL_IN, IN, "an email arrives"),
    EventType(CONNECTOR_MSG, IN, "a chat message arrives (WhatsApp, Telegram…)"),
    EventType(CLUSTER_MSG, IN, "a message from another agent of his network"),
    EventType(CRON_DUE, IN, "a scheduled moment comes"),
    # ── the engine's own ──
    EventType(WORKER_DONE, TASK, "a task of his ended"),
    EventType(WORKER_ASK, TASK, "a task of his asks him something"),
    # ── leaves: a message ──
    EventType("messaging.send_new", OUT, "a message is sent to someone", grant="message", level="sensitive",
              effect="external.send"),
    EventType("messaging.autorespond", OUT, "a message is answered automatically", grant="message", level="sensitive",
              effect="external.send"),
    # ── leaves: his agenda, as seen by the people in it ──
    EventType("calendar.invite_agreed", OUT, "an invitation to a meeting already agreed with its guests",
              grant="schedule", level="sensitive", effect="external.send"),
    EventType("calendar.invite_new_party", OUT, "an invitation that puts somebody new in a meeting",
              grant="schedule", level="sensitive", effect="external.send"),
    EventType("calendar.reschedule_committed", OUT, "a meeting somebody else holds is moved",
              grant="schedule", level="sensitive", effect="data.write"),
    # ── leaves: a site, his accounts, his money ──
    EventType("web.commit", OUT, "a click that commits him on a website (a booking, an order)", level="sensitive"),
    EventType("payment.authorize", OUT, "money leaves his accounts", level="critical"),
    EventType("account.disconnect", OUT, "one of his connected accounts is disconnected", level="sensitive"),
    # ── leaves: an errand ──
    EventType("errand.mesh_serve", OUT, "an errand's request goes to an agent of the network that serves it",
              level="standard"),
    EventType("errand.start", OUT, "an errand starts from a line not clearly addressed to the assistant",
              level="standard"),
    EventType("errand.sends_for_him", OUT, "an errand that will send something in his name (a reading carried with the "
              "task; the send itself is decided at its exit, `messaging.send_new@<channel>`)", grant="message",
              level="sensitive"),
    EventType("errand.moves_money", OUT, "an errand that pays, buys or subscribes with his money", level="critical"),
    EventType("errand.account_change", OUT, "an errand that changes, cancels or closes one of his accounts",
              level="critical"),
)

_BY_NAME = {t.name: t for t in TYPES}


def bare(name: str) -> str:
    """`<family>.<act>` of a key that may carry its channel (`a.b@c`)."""
    return str(name or "").strip().partition("@")[0].strip().lower()


def of(name: str) -> EventType | None:
    """The declared type of this name (channel stripped), or None: an undeclared name is nobody's event."""
    return _BY_NAME.get(bare(name))


def declared(name: str) -> bool:
    return of(name) is not None


def names(direction: str = "") -> list[str]:
    """Every declared type name, or those of one direction, in declaration order."""
    return [t.name for t in TYPES if not direction or t.direction == direction]


def topics() -> tuple[tuple[str, str], ...]:
    """What a standing rule may subscribe to: the types that ARRIVE, each with what it means (`rules.subscriptions`)."""
    return tuple((t.name, t.what) for t in TYPES if t.direction == IN)


def level_of(name: str, default: str = "sensitive") -> str:
    """A leaving type's default sensitivity, for a caller that measured none."""
    t = of(name)
    return (t.level if t and t.level else default)


def grant_of(name: str) -> str:
    """The grant that covers a leaving type ("" when none does)."""
    t = of(name)
    return t.grant if t else ""


def effect_of(name: str) -> str:
    """What an action of this class carries, for the manifest reader ("" when the class declares none)."""
    t = of(name)
    return t.effect if t else ""


def grants_of(may) -> list[str]:
    """Words of a mandate's `may` as GRANTS' names: each word as its grant, unknown words dropped (a grant nothing
    reads is no grant)."""
    out: list[str] = []
    for w in may if isinstance(may, (list, tuple, set)) else []:
        w = str(w).strip().lower()
        g = next((g.name for g in GRANTS if w == g.name or w in g.older), "")
        if g and g not in out:
            out.append(g)
    return out
