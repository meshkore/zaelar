"""rules/subscriptions.py — a rule that says «when X arrives, do Y» is a SUBSCRIPTION (V2-851 F4, V2-848).

Rules were passive rows: read by consent, by the prompt, by a widget — nothing RAN on one. A rule whose shape is «when
a mail from X arrives, put a task in my agenda» now has that shape as DATA: a row `pref` / `on_event` whose value is

    {"topic": "mail.in", "match": {"sender": "billing@acme.example"}, "do": "<his words>", "may": ["agenda"],
     "if": "<an optional pre-condition in his words>", "from_note": "<the note it was read from>"}

The router (`nucleo.turn.flow_events`) matches it IN CODE on the event's declared fields — the same name, compared
exactly — never on words. A pre-condition («only if it is not advertising») is not code either: it is a declared
verdict asked of the event when the rule matches (`precondition`), recorded in the flow by the classifier's own event.

His sentence is understood ONCE: a spoken rule is kept as a `note` (`rules.shape`), and the first time an event of a
topic arrives every note not yet read is read by one structured model call (`shape_notes`, the `rule_shape` seat). A
note that is a subscription gets its derived row (`<note id>~ev`); one that is not is marked read and never asked
again. A derived row lives only while its note does — removing the rule he said removes what it subscribed.
"""
from __future__ import annotations

import json
import re

KEY = "on_event"
_READ = "on_event:read:"            # store marker: this note was read once (subscription or not)
#: The topics a note may subscribe to, with what each means — the model's whole vocabulary, declared once.
TOPICS = (
    ("mail.in", "an email arrives"),
    ("connector.msg", "a chat message arrives (WhatsApp, Telegram…)"),
    ("cluster.msg", "a message from another agent of his network"),
    ("cron.due", "a scheduled moment comes"),
)

_SYSTEM = """You read ONE standing rule the operator gave his assistant and say whether it asks to act WHEN SOMETHING
ARRIVES. Answer with ONE JSON object and nothing else:
{"topic": "<one of TOPICS, or empty>", "match": {"<field>": "<value>"}, "do": "<what to do, in his words>",
 "may": ["<act>"], "if": "<a condition on the arriving item he stated, in his words, or empty>"}
- match: only what he named, exactly as he wrote it. Fields: sender (the address or phone of who sends it),
  platform (email, whatsapp, telegram), name (the sender's name).
- may: the acts the rule lets the assistant do without asking him, from the ACTS below (their names only).
- A rule that is not about something arriving: topic "".
TOPICS:
"""


def _acts() -> str:
    """The grant vocabulary the model picks `may` from — the mandate's own, declared once (`nucleo/errands/mandate.MAY`)."""
    from nucleo.errands import mandate
    return "\nACTS:\n" + "\n".join(f"- {a}: {what}" for a, what, _older in mandate.MAY)


def _log(msg: str) -> None:
    from loguru import logger
    logger.info(f"rules.subscriptions: {msg}")


def _chat(system: str, user: str) -> str | None:
    from nucleo.memory_agent.processor import llm
    return llm.chat_sync("rule_shape", system, user, max_tokens=400, temperature=0.0, timeout=20.0)


def _notes() -> list[dict]:
    import rules
    from . import cascade
    return [r for r in rules.all_rows(include_defaults=False)
            if r["source"] == "user" and r["key"] == cascade.NOTE and cascade.live(r)]


def unread_notes() -> list[dict]:
    """His live notes not yet read for a subscription."""
    from . import store
    return [r for r in _notes() if not store.once_done(_READ + r["id"])]


def parse(content: str) -> dict:
    """The model's answer → a validated subscription value, or {} (not a subscription / unusable)."""
    m = re.search(r"\{.*\}", content or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    topic = str((data or {}).get("topic") or "").strip() if isinstance(data, dict) else ""
    if topic not in dict(TOPICS):
        return {}
    match = {str(k): str(v).strip() for k, v in dict(data.get("match") or {}).items() if str(v or "").strip()}
    from nucleo.errands import mandate
    may = mandate.acts([str(a).strip() for a in (data.get("may") or []) if str(a or "").strip()])[:6]
    return {"topic": topic, "match": match, "do": str(data.get("do") or "").strip()[:600], "may": may,
            "if": str(data.get("if") or "").strip()[:300]}


def shape_notes(*, chat=None) -> int:
    """Read every unread note once; write the derived row of each that is a subscription. Blocking (a model call per
    note): call it off the loop. Returns how many subscriptions were written."""
    import rules
    from . import store
    n = 0
    topics = "\n".join(f"{t} — {what}" for t, what in TOPICS)
    for note in unread_notes():
        try:
            content = (chat or _chat)(_SYSTEM + topics + _acts(), f"RULE ({note['scope']}): {note['text'] or note['value']}")
        except Exception as e:  # noqa: BLE001 — no model now: the note stays unread and is asked next time
            _log(f"note {note['id']} not read ({type(e).__name__}: {e})")
            continue
        sub = parse(content or "")
        if sub:
            rules.add(note["scope"], "pref", KEY, {**sub, "from_note": note["id"]}, text=note["text"],
                      rule_id=f"{note['id']}~ev", origin="on_event")
            n += 1
            _log(f"note {note['id']} subscribes to {sub['topic']} {sub['match']}")
        store.mark_done(_READ + note["id"])
    return n


def rows(topic: str) -> list[dict]:
    """The live subscriptions to `topic` whose note (when they came from one) still exists."""
    import rules
    from . import cascade
    out = []
    for r in rules.all_rows(include_defaults=False):
        v = r.get("value") if isinstance(r.get("value"), dict) else {}
        if r["key"] != KEY or v.get("topic") != topic or not cascade.live(r):
            continue
        if v.get("from_note") and rules.get(v["from_note"]) is None:
            continue
        out.append(r)
    return out


def matches(row: dict, ev: dict) -> bool:
    """Does the event carry every field the subscription names, with the same value? Exact, case-insensitive; a
    field the event does not declare is no match. A subscription that names nothing matches every event of its topic."""
    want = dict((row.get("value") or {}).get("match") or {})
    have = dict((ev or {}).get("fields") or {})
    return all(str(have.get(k) or "").strip().casefold() == str(v).strip().casefold() and have.get(k) not in (None, "")
               for k, v in want.items())


PRECONDITION = "event_precondition"


def precondition(row: dict, ev: dict, *, ask=None) -> bool:
    """A subscription's pre-condition («only if it is not advertising») is a DECLARED VERDICT of the classifier on the
    event's text, recorded by its own event — never a condition in code. No condition → True; an unsure or failed
    verdict → False (a rule that may act on a third party's item does not act on a shrug)."""
    cond = str((row.get("value") or {}).get("if") or "").strip()
    if not cond:
        return True
    from nucleo import jev
    from nucleo.turn import verdicts as _v
    q = {PRECONDITION: {"instructions": f"Does this arriving item meet the condition «{cond}»?",
                        "criteria": {"yes": "it meets the condition", "no": "it does not"}}}
    state = f"{(ev.get('fields') or {}).get('subject') or ''}\n{ev.get('text') or ''}"[:3000]
    handle = (ask or jev.choose_many_sync)(state, q, question_id=PRECONDITION)
    choice, _info = _v.read(handle, PRECONDITION, "no")
    return choice == "yes"
