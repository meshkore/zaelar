"""nucleo/workers/exit_slots.py — one question per DECLARED slot of an act that leaves (V2-857 phase 5, second slice).

The exit door used to stack a reader per incident on top of each other: the recipient put back in his word, the
channel his turn named, his order over the held row, and a `rows.` prefix that skipped the first two. Each is one
answer to the same question — «does this slot of the leaving act come from his words / the task's reading, or from a
stranger?» — so the card now DECLARES its slots and where each must come from, in its manifest:

    "slots": {"recipient": {"key": "contact", "from": "his_words"},
              "channel":   {"key": "channel", "from": "reading"},
              "text":      {"key": "text",    "from": "composed"}}

`from` names a rule of the closed table below (the mechanism, written once); a card names a rule, never a reader, so
a new card that leaves needs no new code here:

  · `his_words` — the value must be in his words for this errand (`message.is_his`); one the worker swapped for a
    name he never said goes back to HIS word (`message.his_recipient`), so the card asks «which one»;
  · `reading`   — the commissioning turn's reading names it (`message_channel.his_channel`): his sure reading
    replaces the call's own;
  · `held`      — the row he saw and surely ordered (`message.confirmed`): his order over it is the yes;
  · `card`      — the card itself answers it (a list number the card turns into a person): read, never rewritten;
  · `composed`  — the worker writes it (a body): read, never rewritten.

Each slot's SOURCE is what the door records: `his`, `reading`, `held`, `card`, `agent` (the worker's own, with no
stranger's text read this session), `stranger` (the worker's own after the session read a stranger's text — what the
taint question then asks about) or `none` (empty). A call through the generic `rows.*` door fills the card's own row:
its slots are the card's and no rule rewrites them. A card that declares no `slots` gets the defaults its payload
declaration implies (`DEFAULTS`), so a fork of a card keeps the door it had.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

#: Rule order: the rewriting rules first, the held row last, over the call as it will run.
ORDER = ("his_words", "reading", "card", "composed", "held")
#: The slots an undeclared leaving action gets from its payload declaration: `{payload key: (slot, rule)}`.
DEFAULTS = {"contact": ("recipient", "his_words"), "channel": ("channel", "reading")}


@dataclass
class Reading:
    inner: dict                                   # the call's payload as it may run
    sources: dict = field(default_factory=dict)   # {slot: source}
    released: bool = False                        # a `held` slot read his order over the row he saw


def declared(wid: str, act: str) -> dict:
    """`{slot: {"key": …, "from": …}}` for this action: its manifest's `slots`, else the payload's defaults."""
    try:
        from nucleo import on_his_behalf as _ob
        spec = _ob._spec(wid, act)
        own = spec.get("slots")
        if isinstance(own, dict) and own:
            return {str(k): v for k, v in own.items() if isinstance(v, dict) and str(v.get("from") or "") in RULES}
        from nucleo.flash import payload_fill
        pl = payload_fill._payload_spec(wid, act)
        return {slot: {"key": key, "from": rule} for key, (slot, rule) in DEFAULTS.items() if key in pl}
    except Exception as e:  # noqa: BLE001 — unread slots rewrite nothing; the leave rule and the taint still ask
        logger.debug(f"exit_slots: slots of {wid}:{act} unread ({e!r})")
        return {}


def read(rec, wid: str, act: str, inner: dict, *, said: str, turn, call: dict, emit) -> Reading:
    """Ask each declared slot where its value comes from, in `ORDER`; rewrite where its rule says so. `call` is the
    bridge's `widget_data` call: through the generic `rows.*` door its slots are the card's row."""
    row_call = str((call or {}).get("action") or "").startswith("rows.")
    from nucleo.workers import taint
    out = Reading(dict(inner or {}))
    ctx = {"rec": rec, "wid": wid, "act": act, "said": said, "turn": turn, "emit": emit,
           "tainted": taint.tainted(rec), "row_call": row_call}
    slots = declared(wid, act)
    for rule in ORDER:
        for slot, d in slots.items():
            if str(d.get("from") or "") == rule and rule in RULES:
                RULES[rule](ctx, out, slot, str(d.get("key") or slot))
    if out.released:   # the row he saw and ordered carries the rest of what leaves
        out.sources = {s: ("held" if v in ("agent", "stranger") else v) for s, v in out.sources.items()}
    return out


def _own(ctx: dict, value) -> str:
    if not str(value or "").strip():
        return "none"
    return "stranger" if ctx["tainted"] else "agent"


def _his_words(ctx: dict, out: Reading, slot: str, key: str) -> None:
    if ctx["row_call"]:
        out.sources[slot] = "card"
        return
    from nucleo.acts import message
    mine = message.his_recipient(ctx["wid"], ctx["act"], out.inner, ctx["said"], key=key,
                                 emit=lambda _k, label, text="", **kw: ctx["emit"](label, text, kw.get("extra") or {}))
    if isinstance(mine, dict):
        out.inner = mine
    v = out.inner.get(key)
    his = isinstance(v, str) and v.strip() and message.is_his(v, [ctx["said"]])
    out.sources[slot] = "his" if his else _own(ctx, v)


def _reading(ctx: dict, out: Reading, slot: str, key: str) -> None:
    if ctx["row_call"]:
        out.sources[slot] = "card"
        return
    from nucleo.acts import message_channel
    theirs = message_channel.his_channel(ctx["wid"], ctx["act"], out.inner, ctx["turn"],
                                         emit=lambda _k, label, text="", **kw: ctx["emit"](label, text, kw.get("extra") or {}))
    named = theirs is not out.inner or _named_by_reading(ctx["turn"], out.inner.get(key))
    if isinstance(theirs, dict):
        out.inner = theirs
    out.sources[slot] = "reading" if named else _own(ctx, out.inner.get(key) or out.inner.get("platform"))


def _named_by_reading(turn, value) -> bool:
    """Does the turn's reading name this very value (the call already carried what he said)?"""
    if turn is None or not str(value or "").strip():
        return False
    from nucleo.acts import message_channel
    from nucleo.turn import verdicts
    choice, _info = verdicts.read(turn, message_channel.KEY, None)
    return choice not in (None, message_channel.NONE) and str(choice) == str(value).strip().lower()


def _card(ctx: dict, out: Reading, slot: str, key: str) -> None:
    out.sources[slot] = "card" if str(out.inner.get(key) or "").strip() or ctx["row_call"] else "none"


def _composed(ctx: dict, out: Reading, slot: str, key: str) -> None:
    out.sources[slot] = "card" if ctx["row_call"] else _own(ctx, out.inner.get(key))


def _held(ctx: dict, out: Reading, slot: str, key: str) -> None:
    """His sure order over the row he saw: the commissioning turn's verdicts, or — for words relayed into a live
    worker, whose turn is not the task's — the order that turn recorded over the same row."""
    from nucleo.acts import message
    wid, act, inner, turn = ctx["wid"], ctx["act"], out.inner, ctx["turn"]
    if (turn is not None and message.confirmed(wid, act, inner, turn)) or message.confirmed(wid, act, inner, None):
        out.released = True
        out.sources[slot] = "held"
    else:
        out.sources[slot] = _own(ctx, inner.get(key) or inner.get("contact"))


#: The closed table of source rules a manifest's `slots` may name.
RULES = {"his_words": _his_words, "reading": _reading, "held": _held, "card": _card, "composed": _composed}
