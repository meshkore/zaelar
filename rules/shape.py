"""rules/shape.py — a spoken rule is UNDERSTOOD once, when it is written (V2-806).

ONE structured model call (the `rule_shape` seat of `nucleo/memllm.py`: off the voice turn, strict JSON, reasoning
off, a stand-in rung) is handed his sentence, the declared vocabulary (`rules/vocabulary.py`) and his current rows,
and answers what to do: add rows, remove rows BY ID, list them, or nothing. Code then VALIDATES every field against
declared data — a scope nobody declared becomes the nearest declared ancestor, a value outside its key's domain is
dropped — and the model is never asked again: the cascade reads the rows on every turn without it.

When no model answers, the sentence is kept as a `note` at `global`: what every spoken rule was before scopes
existed. Nothing he said is lost; nothing is guessed into a gate.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from . import cascade as _cascade
from . import scope as _scope
from . import vocabulary as _vocab
from nucleo import consequence as _consequence

_SYSTEM = """You turn what the operator just said about how his assistant must behave into rows of a rules table.
Answer with ONE JSON object and nothing else:
{"op": "add"|"remove"|"list"|"none",
 "rows": [{"scope": str, "kind": "gate"|"pref", "key": str, "value": any, "except": [str], "until": null|"end_of_day"|"<ISO local datetime>"}],
 "remove": [id], "doubt": [id],
 "say": "<ONE short sentence in HIS language restating what you understood, e.g. «Entendido: no te pido confirmación para los correos, salvo a clientes»>"}
- scope: the NARROWEST scope in SCOPES that matches what he named; "global" only when he names nothing narrower. A rule
  about one act on any channel uses that act's "*" scope; about one channel, that channel's scope.
- gate/consent: may the assistant act without asking? allow = no confirmation, ask = ask first, never = refuse.
- gate/ask_at at "global": the lowest level in LEVELS that asks even for a clear order ("ask before anything" =
  sensitive, "stop asking me" = critical).
- pref at "voice" with a key from KNOBS: how the agent speaks, typed like the knob's current value.
- anything else he wants that no key captures: kind pref, key "note", value = his words, at the scope it is about.
- a negation in the same clause reverses the meaning ("never send an email without asking me" = ask).
- his name, the assistant's name, or how to address him (tú/usted) is NOT a rule: op "none".
- op "remove": he wants a rule gone — list the ids of HIS RULES it refers to in "remove"; if several could be meant and
  he did not say all of them, put them in "doubt" instead.
- op "list": he asks which rules he has.
- "until" only when he bounds it in time ("today" = "end_of_day")."""


def _log(msg: str) -> None:
    import logging
    logging.getLogger("zaelar.rules").info(f"rules.shape: {msg}")


def _chat(system: str, user: str) -> str | None:
    from nucleo.memory_agent.processor import llm
    return llm.chat_sync("rule_shape", system, user, max_tokens=900, temperature=0.0, timeout=20.0)


def _levels() -> tuple:
    from nucleo import consent
    return consent.LEVELS


def his_rows() -> list[dict]:
    """His stored rows (live or not) — what a removal or a listing may name, by id."""
    import rules
    return [r for r in rules.all_rows(include_defaults=False) if r["source"] == "user"]


def _user_message(sentence: str, context: str = "") -> str:
    scopes = "\n".join(f"{k} — {v}" for k, v in _vocab.scopes().items())
    knobs = ", ".join(f"{k} = {json.dumps(v)}" for k, v in _vocab.knobs().items())
    mine = "\n".join(f"{r['id']} | {r['scope']} | {r['key']} = {json.dumps(r['value'], ensure_ascii=False)} | "
                     f"«{r['text'][:120]}»" for r in his_rows()) or "(none)"
    ctx = f"\nWHAT HE WAS ANSWERING: {context[:300]}" if context and context.strip() != sentence.strip() else ""
    return (f"SCOPES:\n{scopes}\n\nKNOBS: {knobs}\nLEVELS: {', '.join(_levels())}\n\nHIS RULES:\n{mine}\n\n"
            f"NOW: {datetime.now().strftime('%Y-%m-%d %H:%M')}{ctx}\n\nSENTENCE: {sentence[:1200]}")


def _until(v) -> float | None:
    if v in (None, "", "null"):
        return None
    if str(v).strip().lower() == "end_of_day":
        return datetime.now().replace(hour=23, minute=59, second=59, microsecond=0).timestamp()
    try:
        return datetime.fromisoformat(str(v).strip()).timestamp()
    except ValueError as e:
        _log(f"an unreadable until ({e}) — the row is kept without one")
        return None


def _typed(value, like):
    """A knob's value, coerced to the type of its genesis value; None when it cannot be."""
    if isinstance(like, bool):
        return value if isinstance(value, bool) else None
    if isinstance(like, int):
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            _log(f"a knob value that is not a number ({e}) — the row is dropped")
            return None
    return str(value) if isinstance(value, (str, int, float)) else None


def _valid_row(raw: dict, sentence: str) -> dict | None:
    """One answered row, checked against declared data. None = dropped."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "").strip()
    value = raw.get("value")
    sc = _vocab.nearest(raw.get("scope") or _scope.GLOBAL)
    knobs = _vocab.knobs()
    if key in ("consent", "ask_at"):
        value = str(value).strip().lower()
        if value not in (_cascade.GATE_VALUES if key == "consent" else _levels()):
            return None                  # a gate outside its domain is not a rule anybody can apply
        kind, sc = "gate", (sc if key == "consent" else _scope.GLOBAL)
    elif key in knobs:
        kind, sc, value = "pref", _scope.VOICE, _typed(value, knobs[key])
        if value is None:
            return None
    else:
        kind, key, value = "pref", _cascade.NOTE, str(value if isinstance(value, str) and value.strip() else sentence)
    excepts = [_vocab.nearest(e) for e in (raw.get("except") or []) if isinstance(e, str) and e.strip()]
    excepts = [e for e in excepts if e != _scope.GLOBAL and e != sc]
    return {"scope": sc, "kind": kind, "key": key, "value": value, "except": excepts, "until": _until(raw.get("until"))}


def parse(content: str, sentence: str) -> dict:
    """The model's answer → a validated plan `{op, rows, remove, doubt, say}`. Unusable → `{"op": ""}`."""
    m = re.search(r"\{.*\}", content or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or data.get("op") not in ("add", "remove", "list", "none"):
        return {"op": ""}
    ids = {r["id"] for r in his_rows()}
    rows = [x for x in (_valid_row(r, sentence) for r in (data.get("rows") or [])) if x]
    return {"op": data["op"], "rows": rows if data["op"] == "add" else [],
            "remove": [i for i in (data.get("remove") or []) if i in ids],
            "doubt": [i for i in (data.get("doubt") or []) if i in ids],
            "say": str(data.get("say") or "").strip()[:300]}


def plan(sentence: str, context: str = "", *, chat=None) -> dict:
    """ONE model call → a validated plan. Blocking: call it in a thread. `chat(system, user)` is injectable."""
    try:
        content = (chat or _chat)(_SYSTEM, _user_message(sentence, context))
    except Exception as e:  # noqa: BLE001 — no model: the caller keeps the sentence as a note
        import logging
        logging.getLogger("zaelar.rules").warning(f"rules: the rule could not be shaped ({e})")
        content = None
    return parse(content or "", sentence)


@_consequence.door("rules.write", neutral=lambda *_a, **_k: {
    "op": "dry", "stored": [], "removed": [], "doubt": [], "listed": [], "say": ""})
def write(sentence: str, context: str = "", *, chat=None) -> dict:
    """Understand his sentence and apply it to the table. Returns what happened, for the caller to say and emit:
    `{op, stored: [rows], removed: [rows], doubt: [rows], listed: [rows], say}`."""
    import rules
    s = " ".join(str(sentence or "").split()).strip()
    out = {"op": "none", "stored": [], "removed": [], "doubt": [], "listed": [], "say": ""}
    if not s:
        return out
    p = plan(s, context, chat=chat)
    if not p.get("op"):
        out.update(op="add", stored=[rules.add(_scope.GLOBAL, "pref", _cascade.NOTE, s, text=s)])
        return out
    mine = {r["id"]: r for r in his_rows()}
    out.update(op=p["op"], say=p["say"])
    if p["op"] == "add":
        out["stored"] = [rules.add(r["scope"], r["kind"], r["key"], r["value"], text=s, except_=r["except"],
                                   until=r["until"]) for r in p["rows"]]
    elif p["op"] == "remove":
        if p["doubt"]:
            out["doubt"] = [mine[i] for i in p["doubt"]]
        else:
            out["removed"] = [x for x in (rules.remove(i) for i in p["remove"]) if x]
    elif p["op"] == "list":
        out["listed"] = [r for r in mine.values() if _cascade.live(r)]
    return out


def listing_line(rows: list[dict]) -> str:
    """His rows as he reads them, grouped by where they apply — never a scope, a key or an id (`rules/labels.py`)."""
    from .labels import grouped_line
    return grouped_line(rows)
