#
# selection.py — PROGRESSIVE SELECTION of the widget catalog (V2-085).
#
# THE PROBLEM (measured 2026-08-01, with only 16 widgets): `brief.for_prompt()` put the WHOLE catalog in EVERY turn
# prompt (2,497 chars) and `GET /widgets` returned all 16 COMPLETE manifests (25,639 chars). Both grow O(N): with
# 1,000 widgets, a "what time is it?" prompt would carry ~150 KB of irrelevant catalog, and with 10,000 the turn would
# be infeasible (cost, latency, and —worse— decision noise for a small model).
#
# THE RULE: **what the model sees is O(K), not O(N).** Growing the catalog must NOT bloat a request turn that is not
# about widgets. This module is the only place deciding WHICH widgets enter a turn prompt.
#
# HOW — layers from LESS to MORE, by PRIORITY (extends the V2-078 ladder, does not replace it):
#
#   1. `open`   — EVERYTHING the operator has IN FRONT OF THEM. Never clipped: it is their screen, the source of truth.
#   2. `named`  — what the operator NAMES in this turn's phrase, resolved by `runtime.rank()` (name/alias, V2-082).
#                 **This is the layer that makes thousands of widgets viable**: a widget at catalog position 4,000 is
#                 PROMOTED to the prompt as soon as the operator names it. Without it, clipping the catalog would be
#                 amnesia; with it, it is focus.
#   3. `recent` — the MRU (`state.recent_widgets`): what was just used, even if no longer open (V2-078).
#   4. `fill`   — fill from the rest of the catalog, in order, ONLY until the budget is exhausted. Courtesy
#                 (discoverability: "what can you do?"), not a correctness requirement — hence first to fall.
#
# WHAT IT **DOES NOT** DO (deliberate — operator invariant, `feedback_no_hardcoded_understand`): it does NOT classify
# intent with verb tables or keywords. It does not decide whether the turn "is about widgets"; it only RETRIEVES the
# most plausible candidates and lets the model (function-calling) decide. Retrieval ≠ understanding.
#
# ESCAPE HATCH (why clipping is SAFE): `show_widget` and `widget_data` resolve their argument server-side with
# `runtime.identify()` against the COMPLETE catalog (see `providers/nucleo.py`). If the operator names something that
# did not appear in the prompt, layer 2 will almost always have promoted it; and if not, the model can pass the
# operator's words as-is and the server resolves them anyway. Clipping the prompt NEVER clips what the system can open.
#
from __future__ import annotations

from . import runtime

# HARD turn budgets. They are the contract: whatever happens to the catalog, this is the maximum prompt cost the
# operator pays for the widget layer.
# K = row ceiling in the prompt. Chosen so TODAY nothing changes (the real catalog has 16 widgets → all fit, identical
# prompt to before: zero regression for the operator) while the O(K) guarantee is written in code. The exact value
# matters little; what matters is that a ceiling EXISTS — correctness does not depend on it, but on the `named` layer,
# which promotes what the operator names regardless of its position.
MAX_WIDGETS = 20
MAX_RECENT = 4              # how many MRU items enter (the rest of MRU is noise: no longer on screen)
MAX_NAMED = 4               # how many name/alias candidates are promoted (more means ambiguity → ask)
MAX_OPEN = 10               # defensive ceiling: an operator with 40 open widgets must not blow the budget

# Reason each widget entered — noted in the prompt row and recorded in stats (observability).
OPEN, NAMED, RECENT, FILL = "open", "named", "recent", "fill"


def _norm_ids(seq) -> list[str]:
    """Lowercase ids, without empties, duplicates, or instance suffix (`navegador::t1` → `navegador`)."""
    out, seen = [], set()
    for i in (seq or []):
        i = str(i or "").split("::", 1)[0].strip().lower()
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def candidates(query: str = "", open_ids=None, recent_ids=None, *,
               max_widgets: int = MAX_WIDGETS, stats: dict | None = None) -> list[dict]:
    """Widgets that enter THIS turn's prompt, already ordered by priority and bounded to `max_widgets`.

    Returns `[{"w": <manifest>, "reason": open|named|recent|fill}]`. Output order IS priority order
    (open → named → recent → fill), which is also the hint the model reads to break ties.

    `stats` (optional, `timings` pattern from the rest of core): output dict with observability breakdown — n_total,
    n_selected, how many per layer, how many remained hidden, and whether truncation happened.

    Best-effort end to end: a broken catalog or corrupt widget degrades the turn, never breaks it."""
    try:
        cat = list(runtime.catalog())
    except Exception:
        cat = []
    by_id = {str(w.get("id") or "").strip().lower(): w for w in cat if w.get("id")}
    n_total = len(by_id)

    opened = _norm_ids(open_ids)
    recent = [r for r in _norm_ids(recent_ids) if r not in set(opened)]

    picked: list[dict] = []
    taken: set[str] = set()

    def _take(wid: str, reason: str) -> bool:
        w = by_id.get(wid)
        if w is None or wid in taken or len(picked) >= max_widgets:
            return False
        taken.add(wid)
        picked.append({"w": w, "reason": reason})
        return True

    # 1) OPEN — what is in front of the operator. First and non-negotiable (defensive ceiling aside).
    for wid in opened[:MAX_OPEN]:
        _take(wid, OPEN)

    # 2) NAMED in the turn phrase — the layer that supports thousands of widgets.
    n_ranked = 0
    if query:
        try:
            ranked = runtime.rank(query, limit=MAX_NAMED)
        except Exception:
            ranked = []
        n_ranked = len(ranked)
        for _score, w in ranked:
            _take(str(w.get("id") or "").strip().lower(), NAMED)

    # 3) RECENTLY USED (MRU) — continuity across turns even if already closed.
    for wid in recent[:MAX_RECENT]:
        _take(wid, RECENT)

    # 4) FILL — discoverability, and only if there is remaining budget. First to fall as the catalog grows.
    for wid in by_id:
        if len(picked) >= max_widgets:
            break
        _take(wid, FILL)

    if stats is not None:
        counts = {r: 0 for r in (OPEN, NAMED, RECENT, FILL)}
        for p in picked:
            counts[p["reason"]] += 1
        stats.update({
            "n_total": n_total,
            "n_selected": len(picked),
            "n_open": counts[OPEN],
            "n_named": counts[NAMED],
            "n_recent": counts[RECENT],
            "n_fill": counts[FILL],
            "n_ranked": n_ranked,                       # how many name/alias matched (before MAX_NAMED ceiling)
            "hidden": max(0, n_total - len(picked)),
            "truncated": len(picked) < n_total,
            "selected_ids": [str(p["w"].get("id") or "") for p in picked],
        })
    return picked
