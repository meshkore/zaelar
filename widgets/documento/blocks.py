"""The document's text read as BLOCKS (headings, paragraphs) and the bound errand's PROCESS view.

Split out of `data.py`: the units the card renders and `goto` aims at, the section outline `view_data` declares,
and the narrative derived from the dispatcher's live record of a REPORT errand (V2-644).
"""
from __future__ import annotations

#: The process view keeps the same bounds as the results sheet's live view (`widgets/results/live.py`).
_MAX_PHASES = 40
_MAX_PHASE_CHARS = 160


def _clean_phases(raw) -> list:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:_MAX_PHASE_CHARS] for x in raw if str(x or "").strip()][-_MAX_PHASES:]


def _process(db: dict):
    """The PROCESS view of the bound errand — derived from the dispatcher's live record on every read, exactly
    like the results sheet's Proceso tab (`widgets/results/live.py`): storing it would leave a stale copy on
    screen. Once the errand is over, the history persisted by `finish_task` is what remains. `None` means this
    sheet was never an errand's surface — the widget then renders as the plain document it always was.

    Fail-soft on purpose: without a dispatcher (the bare render harness, a test), a bound task shows its
    stored history and `alive: False`, which is exactly what is true from here.

    Always a dict (never None): the golden pins the SHAPE of view_data, and a key that flips between
    NoneType and dict would turn the harness red the first time a live engine had a bound errand. A sheet
    that was never an errand's surface is `{alive: False, phases: []}` — the widget reads that as «no
    process» and renders the plain document it always did."""
    tid = str(db.get("task") or "")
    stored = _clean_phases(db.get("process"))
    if not tid and not stored:
        return {"alive": False, "phases": [], "title": ""}
    live = {}
    if tid:
        try:
            from nucleo import dispatch as _disp
            live = _disp.task_progress(tid) or {}
        except Exception:  # noqa: BLE001
            live = {}
    if live.get("alive"):
        plan = _clean_phases(live.get("plan"))           # V2-820: the worker's declared steps, and how many are done
        return {"alive": True, "phases": _clean_phases(live.get("phases")), "plan": plan,
                "done": max(0, min(int(live.get("done") or 0), len(plan))),
                "title": str(db.get("task_title") or "")}
    return {"alive": False, "phases": stored, "title": str(db.get("task_title") or "")}


def _sections(body: str) -> list:
    out = []
    for b in _blocks(body):
        if b.startswith("#"):
            level = len(b) - len(b.lstrip("#"))
            out.append({"n": len(out) + 1, "title": b.lstrip("# ").strip(), "level": level})
    return out


_STOP = {"the", "and", "that", "with", "this", "from", "show", "section", "part", "where", "which", "what", "about",
         "explaining", "explains", "why", "los", "las", "del", "que", "una", "sobre", "sección", "parte", "donde",
         "enséñame", "muéstrame", "llévame"}


def _blocks(body: str) -> list:
    """Headings on their own, paragraphs as one block each — the units the card renders."""
    out, buf = [], []
    for line in str(body or "").splitlines():
        t = line.strip()
        if t.startswith("#"):
            if buf:
                out.append(" ".join(buf)); buf = []
            out.append(t)
        elif not t:
            if buf:
                out.append(" ".join(buf)); buf = []
        else:
            buf.append(t)
    if buf:
        out.append(" ".join(buf))
    return out


def _best_block(body: str, query: str) -> str:
    """The block that best matches: an exact phrase wins; else most query words, a heading winning a tie."""
    q = str(query or "").strip().lower()
    if not q:
        return ""
    blocks = _blocks(body)
    for b in blocks:
        if len(q) >= 8 and q in b.lower():
            return b.lstrip("# ").strip()
    words = {w.strip(".,;:«»\"'()?¿!¡") for w in q.split()}
    words = {w for w in words if len(w) >= 4 and w not in _STOP}
    if not words:
        return ""
    best, score = "", 0.0
    for i, b in enumerate(blocks):
        low = b.lower()
        n = sum(1 for w in words if w[:6] in low)          # a stem, so «colonies» finds «Colonies», «grievance» «grievances»
        sc = n + (0.5 if b.startswith("#") else 0) - i * 1e-4
        if n and sc > score:
            best, score = b.lstrip("# ").strip(), sc
    return best
