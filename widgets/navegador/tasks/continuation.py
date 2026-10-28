"""«Is this the same errand?»: the words of a goal, their similarity, the live task an order continues.
Moved out of `tasks.py`; the registry's state and every module name are read through the package (`_f.<name>`), so
a patch on `tasks` still governs every call.
"""

import time

from nucleo import matching

from widgets.navegador import tasks as _f


def _words(s: str) -> set:
    import re as _re
    if _f._COEXIST_RE is None:
        # Trim CLAUSES that talk about ANOTHER task ("without stopping the motorcycle task", "without closing X",
        # "apart from the search for Y", "besides Z") — their subject belongs to ANOTHER task and polluted matching
        # (bug 2026-07-13: "dog face WITHOUT STOPPING the motorcycle task" matched the bike because of "motorcycles").
        _f._COEXIST_RE = _re.compile(
            r"\b(sin (parar|detener|cerrar|tocar|cancelar)|aparte de|adem[aá]s de|dejando|manteniendo)\b.*$",
            _re.I)
    s = _f._COEXIST_RE.sub("", (s or "").lower())
    return {w for w in _re.split(r"[^0-9a-záéíóúñ]+", s) if len(w) > 2}


def _similar(g: set, other_goal: str) -> bool:
    """True if word set `g` and `other_goal` are the SAME search. Anchor on the shared SUBJECT (roots len≥4, not
    stopword/marketplace). To avoid merging different topics through an incidental mention (bug 2026-07-13: "dog face
    without stopping the motorcycle task" matched the bike through "motorcycles"), a ONE-word anchor only counts for
    SHORT CLARIFICATIONS (`g` ≤3 content words, e.g. "no, enduro"); a fuller request requires ≥2 shared subjects or
    Jaccard ≥0.4. Two different topics (motorcycle vs apartment, motorcycle vs dog) do not match."""
    gs = {_f._stem(w) for w in g}
    os_ = {_f._stem(w) for w in _f._words(other_goal)}
    if not gs or not os_:
        return False
    shared = gs & os_
    subject = {w for w in shared if len(w) >= 4 and w not in _f._STOP_STEMMED}   # shared subject(s) (moto, enduro, car...)
    # SHORT clarification → 1 subject is enough (keeps "no, enduro" anchored to the bike); fuller request → ≥2.
    # "Short" is measured in CONTENT words (as the contract above says), NOT total words: "no, I want a 300 enduro
    # motorcycle" has filler but its content is 2 words — it is a clarification.
    content = {w for w in gs if len(w) >= 4 and w not in _f._STOP_STEMMED}
    if subject and (len(content) <= 3 or len(subject) >= 2):
        return True
    return matching.jaccard(gs, os_) >= 0.4


def similar_active(goal: str, within: float = _f._ZOMBIE_MAX) -> str | None:
    """Id of an ACTIVE task (queued/working/needs_input) whose objective looks very similar to `goal` — so the SAME
    search does NOT open a SECOND browser even if the operator refines it turns —or MINUTES— later while the browser is
    still working. An active task deduplicates throughout its WHOLE life (up to `within`, only anti-zombie guard).
    Returns None if there is no similar one (two different tasks —motorcycle vs apartment— do NOT merge)."""
    g = _f._words(goal)
    if not g:
        return None
    now = time.time()
    with _f._lock:
        for tid, t in _f._tasks.items():
            if t.get("status") not in ("queued", "working", "needs_input"):
                continue
            if now - t.get("created", 0) > within:   # anti-zombie guard (hung task); NOT a dedup window
                continue
            if _f._similar(g, t.get("goal", "")):
                return tid
    return None


def find_continuation(goal: str) -> tuple[str, str] | None:
    """(tid, status) of the task that this `goal` CONTINUES — so operator CLARIFICATIONS MODIFY the current task
    instead of opening another browser:
      · similar ACTIVE task → refined WHILE RUNNING (the loop re-reads the objective);
      · similar recently FINISHED task (≤_CONTINUATION_MAX) → RE-LAUNCHED in the same card.
    Prioritize active; otherwise the most recent finished one. None if there is no same-topic task (motorcycle vs
    apartment do not match). This is STATE CONTROL: "when I search for a bike and say «no, enduro», modify the task,
    do not open another one"."""
    g = _f._words(goal)
    if not g:
        return None
    now = time.time()
    with _f._lock:
        for tid, t in _f._tasks.items():   # 1) active (priority) → refine while running
            if t.get("status") in ("queued", "working", "needs_input") \
                    and now - t.get("created", 0) <= _f._ZOMBIE_MAX and _f._similar(g, t.get("goal", "")):
                return (tid, t["status"])
        best = None                     # 2) recently finished → re-launch in its card (most recent)
        for tid, t in _f._tasks.items():
            if t.get("status") not in ("done", "failed"):
                continue
            ts = t.get("finished") or t.get("created", 0)
            if now - ts <= _f._CONTINUATION_MAX and _f._similar(g, t.get("goal", "")):
                if best is None or ts > best[2]:
                    best = (tid, t["status"], ts)
        if best:
            return (best[0], best[1])
    return None
