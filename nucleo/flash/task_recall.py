"""nucleo/flash/task_recall.py — «de la tarea de buscar piso que te dije antes» (V2-728 F5).

THE QUESTION NOBODY COULD ANSWER. Disambiguation in this engine reaches only what is on screen right now
(`widgets/instances.py`, pure over `open_ids`) or the six-entry `recent_widgets` MRU. A commission that ended
last week is neither, and its sheet may well have been pruned by the eight-sheet cap. So a reference to it
resolved to nothing, and the turn either opened the wrong card or searched the web again for something the
operator had already paid for.

THE SHAPE IS THE OPERATOR'S OWN RULE (INI-027 §7, 2026-08-31): **an index narrows, a model chooses.**

  1. `memory.tasks_store.task_search` — FTS5 over the title and the goal of every task, accent-insensitive,
     OR-matched and ranked by bm25. No model, no network, ≤5 candidates.
  2. `nucleo/jev.py::select_many` — ONE round trip that scores those candidates against his actual sentence.

Step 2 is the first production consumer of `select_many`, built and measured under V2-726 (recall 3/3 against
100 synthetic listings) and until now called by nothing but its own test. It belongs here rather than on the
hot path for the reason that module states plainly: a Jev verdict lands at ~800 ms, and this runs when the
operator asks to look something up, not while he is mid-sentence.

WHAT IT REFUSES TO DO. With several equally good candidates it ASKS. That is the rule
`widgets/directory.py:176` already keeps for contacts — «two matches are an AMBIGUITY the caller asks about,
never a silent pick» — and it matters more here: opening the wrong report looks exactly like opening the
right one, and he would read it before noticing.
"""
from __future__ import annotations

from nucleo import tasks as _tasks

#: How many candidates the index may hand to the chooser. Five is the operator's number (INI-027 §7) and it
#: is also the point past which ASKING stops being usable: a question listing eight reports is not a question.
MAX_CANDIDATES = 5


def candidates(query: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """The finished commissions this phrase could be about. Lexical only — no model, no network."""
    return _tasks.search(query, limit=limit)


def _label(row: dict) -> str:
    """One candidate as the chooser sees it: what it was called, what was asked, and how it ended."""
    bits = [str(row.get("title") or "").strip(), str(row.get("goal") or "").strip()]
    outcome = str(row.get("outcome") or "").strip()
    if outcome:
        bits.append(f"resultado: {outcome}")
    return " · ".join(b for b in bits if b)[:300]


def resolve(query: str, *, limit: int = MAX_CANDIDATES) -> dict:
    """Which task does this phrase mean?

    Returns one of three answers, and the caller must handle all three:

        {"ok": True,  "task": {...}}                      — one, and we are sure
        {"ok": False, "ask": [{...}, ...]}                — several: ASK, naming them
        {"ok": False, "ask": []}                          — none: say so, do not invent one

    A single candidate is taken WITHOUT asking Jev. The index already agreed it is the only thing he could
    mean, and paying 800 ms to confirm what nothing contradicts is the kind of call V2-726 was written to
    stop making.
    """
    q = (query or "").strip()
    rows = candidates(q, limit=limit)
    if not rows:
        return {"ok": False, "ask": [], "reason": "nada parecido"}
    if len(rows) == 1:
        return {"ok": True, "task": rows[0], "how": "único"}
    try:
        from nucleo import jev as _jev
        picked = _jev.select_many(
            rows,
            criteria=(f"El operador se refiere a una tarea que ya le encargó antes y dice: «{q}». "
                      f"¿Es ESTE el encargo del que habla?"),
            key=lambda r: r["id"], label=_label)
    except Exception:  # noqa: BLE001 — the chooser is advisory; without it we ask, which is the safe answer
        picked = []
    if len(picked) == 1:
        chosen = next((r for r in rows if r["id"] == picked[0]["key"]), None)
        if chosen:
            return {"ok": True, "task": chosen, "how": "jev", "confidence": picked[0].get("confidence")}
    # Nobody fits, or several do equally well. Both are questions, and the SHORTLIST is what makes the
    # question answerable — if Jev narrowed it at all, ask about those and not about all five.
    shortlist = [r for r in rows if any(p["key"] == r["id"] for p in picked)] or rows
    return {"ok": False, "ask": shortlist, "how": "jev" if picked else "índice"}


def reopen(task: dict) -> dict:
    """Put a resolved task's report back on the canvas. `{"ok", "instance", "title", "rebuilt"}`."""
    from widgets.results import rehydrate as _rehy
    return _rehy.sheet_from_task(str(task.get("id") or ""))


def recall_and_reopen(query: str) -> dict:
    """The whole gesture, for the `reopen_task` tool: find it, and show it.

    On an ambiguity it returns the shortlist rather than a card, because the turn has to ASK — and the tool's
    answer is what the model reads to phrase that question.
    """
    r = resolve(query)
    if not r.get("ok"):
        return {"ok": False, "ask": [{"id": x["id"], "title": x.get("title") or x.get("goal") or x["id"]}
                                     for x in r.get("ask", [])]}
    out = reopen(r["task"])
    out["task"] = {"id": r["task"]["id"], "title": r["task"].get("title") or r["task"].get("goal") or ""}
    return out


def voice_turn(query: str) -> dict:
    """The whole gesture as ONE verdict the voice turn can act on without deciding anything itself.

        {"show": "results::<id>"|None, "ask": "a, b, c"|None, "title": str, "rebuilt": bool}

    It lives here rather than in the provider because that file is 114 lines over its own architecture
    ceiling and the ratchet's answer to that is «extract a module, do not raise the ceiling». Everything
    below is a decision, and none of it is about speaking.
    """
    out = recall_and_reopen(query)
    if out.get("ok") and out.get("instance"):
        return {"show": out["instance"], "ask": None, "rebuilt": bool(out.get("rebuilt")),
                "title": str((out.get("task") or {}).get("title") or "")}
    names = ", ".join(str(x.get("title") or "")[:60] for x in (out.get("ask") or [])[:3])
    return {"show": None, "ask": names or None, "rebuilt": False, "title": ""}
