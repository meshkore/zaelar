"""«De la tarea de buscar piso que te dije antes» — a past errand he names, found and brought back (V2-728 F5).

Disambiguation elsewhere reaches only what is on screen or the six-entry MRU; a commission that ended last week is
neither, and its sheet may have been pruned. THE SHAPE IS A DESIGN RULE: **an index narrows, one chooser chooses.**

  1. The ledger narrows: `circuit.ledger.search` — FTS5 over the title and goal of every task, no model, ≤5 rows.
  2. ONE chooser decides (`choose`): a lone candidate is it; a word of his only one candidate's TITLE has names it
     (lexical, no model — «el de Gràcia» over Gràcia and Sant Antoni, `flat-hunt-recall-the-report__es`); else Jev's
     `select_many` scores them against his sentence. Several equally good, or none: it ASKS, never a silent pick —
     opening the wrong report looks exactly like opening the right one.

The TITLE and not the goal: the title is the name he sees on the board, while a goal carries incidental words
(«…under $3,200/month» would make «the one I told you about last MONTH» a pick).
"""
from __future__ import annotations

import re
import unicodedata

from nucleo.circuit import ledger as _tasks

#: How many candidates the index may hand to the chooser; past five, a question listing them is not a question.
MAX_CANDIDATES = 5
#: Shorter words are grammar («que», «del», «the», «you»), not names. Four keeps «sant», «soho», «gracia».
MIN_WORD = 4
#: The chooser ran and rejected every candidate — an ANSWER, not an absence. See `resolve`.
_JEV_NO_MATCH = "no_match"


def words(text: str) -> set[str]:
    """Lower-cased, accent-folded words of at least `MIN_WORD` letters — «Gràcia» and «gracia» are one word."""
    folded = unicodedata.normalize("NFKD", str(text or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", folded) if len(w) >= MIN_WORD}


def named(rows: list[dict], *texts: str, name=lambda r: r.get("title") or r.get("goal") or "") -> dict | None:
    """The one candidate his words name by a word only it has, or None. With ONE candidate, a word of his that its
    name carries is enough. Words every candidate shares tell nothing apart; distinctive words pointing at two
    different candidates are a contradiction, and contradiction is a question, never a pick."""
    said: set[str] = set()
    for t in texts:
        said |= words(t)
    bags = [words(name(r)) for r in rows]
    if len(rows) == 1:
        return rows[0] if said & bags[0] else None
    hits = {owners[0] for w in said if len(owners := [n for n, bag in enumerate(bags) if w in bag]) == 1}
    return rows[hits.pop()] if len(hits) == 1 else None


def candidates(query: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """The finished commissions this phrase could be about, never an INLINE request row (V2-776 M5: ~30 a session,
    and an agenda add is answered by the recent-state block, not by reopening anything)."""
    rows = _tasks.search(query, limit=limit * 3)
    return [r for r in rows if str(r.get("kind") or "") != "inline"][:limit]


def _label(row: dict) -> str:
    """One candidate as the chooser sees it: what it was called, what was asked, and how it ended."""
    bits = [str(row.get("title") or "").strip(), str(row.get("goal") or "").strip()]
    if (outcome := str(row.get("outcome") or "").strip()):
        bits.append(f"resultado: {outcome}")
    return " · ".join(b for b in bits if b)[:300]


def choose(rows: list[dict], query: str, heard: str = "") -> dict:
    """The ONE chooser over the ledger's candidates: `{"ok": True, "task", "how"}` or `{"ok": False, "ask", "how"}`.
    A lone candidate is taken without asking Jev — 800 ms to confirm what nothing contradicts is what V2-726 stopped."""
    if not rows:
        return {"ok": False, "ask": [], "reason": "nada parecido"}
    if len(rows) == 1:
        return {"ok": True, "task": rows[0], "how": "único"}
    # His query, or else his own sentence, which the model may have paraphrased the name out of.
    if (hit := named(rows, query) or named(rows, heard)):
        return {"ok": True, "task": hit, "how": "nombrado"}
    try:
        from nucleo import jev as _jev
        picked, status = _jev.select_many_status(
            rows,
            criteria=(f"El operador se refiere a una tarea que ya le encargó antes y dice: «{query}». "
                      f"¿Es ESTE el encargo del que habla?"),
            key=lambda r: r["id"], label=_label)
    except Exception:  # noqa: BLE001 — the chooser is advisory; without it we ask, which is the safe answer
        picked, status = [], "unavailable"
    if len(picked) == 1 and (chosen := next((r for r in rows if r["id"] == picked[0]["key"]), None)):
        return {"ok": True, "task": chosen, "how": "jev", "status": status, "confidence": picked[0].get("confidence")}
    # Nobody fits, or several do. If Jev narrowed it, ask about those. `how` says whether the chooser looked at all
    # (V2-726 A6a: `[]` used to mean both «rejected all five» and «never ran», which call for opposite answers).
    shortlist = [r for r in rows if any(p["key"] == r["id"] for p in picked)] or rows
    how = "jev" if picked else ("índice" if status == _JEV_NO_MATCH else "sin-chooser")
    return {"ok": False, "ask": shortlist, "how": how, "status": status}


def resolve(query: str, *, limit: int = MAX_CANDIDATES, heard: str = "") -> dict:
    """Which task does this phrase mean? The ledger narrows, `choose` decides; the caller handles all three answers
    (one and sure · several, ask naming them · none, say so)."""
    q = (query or "").strip()
    return choose(candidates(q, limit=limit), q, heard)


def reopen(task: dict) -> dict:
    """Put a resolved task's report back on the canvas. `{"ok", "instance", "title", "rebuilt"}`."""
    from widgets.results import rehydrate as _rehy
    out = _rehy.sheet_from_task(str(task.get("id") or ""))
    return out if out.get("ok") else (_document_of(task) or out)


def _document_of(task: dict) -> dict | None:
    """A REPORT errand's result is the document sheet (V2-644), not a results sheet: it kept no `result` artifact,
    so the sheet rebuild said «no results» and the turn went mute (three-tasks-at-once EN, 2026-10-15)."""
    try:
        from widgets.documento import data as _doc
        db = _doc._load()
    except Exception:  # noqa: BLE001
        return None
    title = str(task.get("title") or task.get("goal") or "").strip()
    bound = str(db.get("task") or "") == str(task.get("id") or "") or (title and str(db.get("task_title") or "") == title)
    if not bound or not str(db.get("body") or db.get("src") or "").strip():
        return None
    return {"ok": True, "instance": "documento", "rebuilt": False, "title": str(db.get("title") or title)}


def recall_and_reopen(query: str, heard: str = "") -> dict:
    """The whole gesture, for the `reopen_task` tool: find it, and show it — or the shortlist, so the turn can ASK."""
    r = resolve(query, heard=heard)
    if not r.get("ok"):
        return {"ok": False, "ask": [{"id": x["id"], "title": x.get("title") or x.get("goal") or x["id"]}
                                     for x in r.get("ask", [])]}
    out = reopen(r["task"])
    out["task"] = {"id": r["task"]["id"], "title": r["task"].get("title") or r["task"].get("goal") or ""}
    return out


def sheet_named_by(query: str) -> dict | None:
    """The one results sheet the phrase names, read by the same chooser over the sheets' faces (a tie is none)."""
    try:
        from widgets.results import sheet_names as _sn
        faces = _sn.recent_faces(limit=8)
    except Exception:  # noqa: BLE001
        return None
    return named(faces, query, name=lambda f: f.get("label") or "")


def voice_turn(query: str, heard: str = "", brief=None) -> dict:
    """The whole gesture as ONE verdict the voice turn acts on without deciding anything itself.

        {"show": …|None, "ask": "a, b, c"|None, "title", "rebuilt", "label", "text", "extra", "escalate"}
    """
    out = recall_and_reopen(query, heard)
    if not out.get("ok") and not out.get("ask"):
        # Demo pass 89, S1 «show me the monitors»: no candidate at that instant (the row was still settling) and the
        # turn said «bringing back those monitors» over an empty screen. The SHEET was there all along (V2-773).
        if (sheet := sheet_named_by(query)):
            out = {"ok": True, "instance": sheet["id"], "rebuilt": False, "task": {"title": sheet["label"]}}
    if out.get("ok") and out.get("instance"):
        v = {"show": out["instance"], "ask": None, "rebuilt": bool(out.get("rebuilt")),
             "title": str((out.get("task") or {}).get("title") or "")}
    else:
        names = ", ".join(str(x.get("title") or "")[:60] for x in (out.get("ask") or [])[:3])
        v = {"show": None, "ask": names or None, "rebuilt": False, "title": ""}
    # Nothing to show and nothing to ask, under a verdict already paid that this ORDER needs a worker: the model read a
    # correction as «bring back the report». The verdict completes the empty act (CRIT-K2).
    from nucleo.flash import direct_action as _da
    v["escalate"] = not v["show"] and not v["ask"] and brief is not None and _da.verdict_escalates(brief)
    v["label"] = ("🗂️ encargo recuperado" if v["show"] else "❓ varios encargos parecidos" if v["ask"]
                  else "↪️ nada que reabrir: el veredicto pide un worker" if v["escalate"] else "🗂️ ningún encargo parecido")
    v["text"] = str(v["title"] or query)[:120]
    v["extra"] = {"id": v["show"] or "", "rebuilt": v["rebuilt"], "cands": v["ask"] or ""}
    return v
