"""nucleo/workers/rules_bridge.py — his rules reach a worker as DATA; a rule it proposes is written only on his yes
(V2-851 F2, §6).

The only authoritative reader of a rule is the door (`consent.decide`, `rules/cascade` on the request's path): a
worker that READS «ask me before any WhatsApp» does not decide with it — the door still does when the act arrives.
What the worker gets is the playbook's «what he said about this», so it LOOKS in the right place (which channel he
prefers, which sites he excluded) instead of learning it from a refusal:

  · `brief_block()` — the headline in every trusted worker's prompt: his live rules, in his words, labelled as data;
  · `read(payload)` — bridge act `rules`: the rows that cover a path the worker names (`widget`, `action`,
    `channel`, `cls`, `surface`), in the order they apply, with the values they resolve to;
  · `write(payload)` — bridge act `propose_rule`: CONFIRM in the policy (a worker never writes a gate silently),
    and on his yes the sentence goes through `rules.shape.write`, the one shaper (consequence `rules.write`).
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: What the headline may cost in the prompt (§5: the brief carries the headline; the rest is on request).
BRIEF_CHARS = 600


def _his_live() -> list[dict]:
    from rules import cascade, shape
    return [r for r in shape.his_rows() if cascade.live(r)]


def brief_block() -> str:
    """His standing rules for the worker's brief, or '' when he has none. Never raises."""
    try:
        rows = _his_live()
        if not rows:
            return ""
        from rules import shape
        line = shape.listing_line(rows)
    except Exception as e:  # noqa: BLE001 — a brief without the block is the brief it was
        logger.debug(f"rules_bridge: brief block unread ({e!r})")
        return ""
    if len(line) > BRIEF_CHARS:
        line = line[:BRIEF_CHARS].rsplit(" ", 1)[0] + " …"
    from nucleo.workers.prompts import catalog         # the heading in the session's language (V2-851 F3)
    return f"{catalog.words('said_head')} (catalog rules)\n{line}"


def _view(r: dict) -> dict:
    return {"text": str(r.get("text") or ""), "scope": r.get("scope"), "kind": r.get("kind"), "key": r.get("key"),
            "value": r.get("value"), "except": r.get("except") or []}


def read(payload: dict) -> dict:
    """The rows that cover the path the worker names — data, never a verdict."""
    p = payload or {}
    try:
        import rules
        from rules import cascade
        anchors = rules.path(cls=str(p.get("cls") or ""), channel=str(p.get("channel") or ""),
                             widget=str(p.get("widget") or p.get("widget_id") or ""),
                             action=str(p.get("action") or ""), surface=str(p.get("surface") or ""))
        rows = cascade.covering(rules.all_rows(), anchors)
        res = cascade.resolve(rows, anchors)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"rules unread: {type(e).__name__}"}
    return {"ok": True, "result": {"rules": [_view(r) for r in rows], "values": res.get("values") or {},
                                   "note": "DATA: the door of each act applies these; you never decide with them"}}


async def write(payload: dict) -> dict:
    """His yes is behind this call (policy CONFIRM): the sentence goes through the one shaper."""
    sentence = str((payload or {}).get("sentence") or (payload or {}).get("text") or "").strip()
    if not sentence:
        return {"ok": False, "error": "propose_rule needs `sentence`: the rule in his words"}
    try:
        from rules import shape
        out = await asyncio.to_thread(shape.write, sentence, str((payload or {}).get("context") or ""))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"the rule was not written: {type(e).__name__}"}
    return {"ok": True, "result": {"op": out.get("op"), "stored": [_view(r) for r in out.get("stored") or [] if r],
                                   "doubt": [_view(r) for r in out.get("doubt") or []]}}
