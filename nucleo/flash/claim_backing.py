"""nucleo/flash/claim_backing.py — what a reply's claim about a candidate may stand on, read once per turn.

The sources a row's name, price or attribute may come from (row-claims guard, 2026-10-14): a row of a recent
results sheet (its whole title, subtitle, price, parts and the facts that carry a value — a hard-requirement fact
only when it reads «yes»), a row the sheet discarded (it exists, it was turned away), his own words and the
`[SISTEMA]` notes pushed into his turns (a worker that finished says what it found there), the in-turn web search
(`amount_gate.search_backing`) and what the live errands report about their step. The assistant's own earlier
words are NOT a source: that is how «8 kilos y clase A» travelled from one turn into the next.

Read lazily by `row_claims` (only a reply that claims something pays for it). Never raises.
"""
from __future__ import annotations

import re
import unicodedata

#: Sheets read for backing: the most recent ones — a sheet of this conversation is among them; old ones only widen.
RECENT_SHEETS = 8
#: A sheet written this recently makes the turn a shortlist turn even with no errand running (the listing fast pass).
SHEET_FRESH_S = 900.0


def fold(text) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def tokens(text) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(text)))


def _fact_text(f: dict, hard_labels: set[str]) -> str:
    from widgets.results import hard_checks as H
    value = str(f.get("value") or "").strip()
    verdict = H.status(value)[0] if value else H.UNVERIFIED
    if verdict == H.NO or not value or value.startswith(H.UNKNOWN):
        return ""                                    # a «no» carries the opposite of any positive claim
    if verdict == H.UNVERIFIED and fold(f.get("label")) in hard_labels:
        return ""                                    # a hard requirement commits only with a «yes» (`row_check`)
    return f"{f.get('label') or ''}: {value}"


def row_text(item: dict, hard: list[str] | tuple = ()) -> str:
    """Everything a row says about itself, the parts and facts included; unknown («?») facts say nothing."""
    hard_labels = {fold(h) for h in hard}
    parts = [item.get(k) for k in ("full_title", "title", "subtitle", "price", "badge")]
    for f in item.get("facts") or []:
        if isinstance(f, dict):
            parts.append(_fact_text(f, hard_labels))
    for p in item.get("parts") or []:
        if isinstance(p, dict):
            parts.append(row_text(p, hard))
    return " · ".join(str(p) for p in parts if p)


def rows_of(view: dict) -> list[dict]:
    """`{"item", "text", "rejected"}` for each row of ONE sheet view: its candidates, then what it turned away."""
    from nucleo.flash import row_ask as _ra
    hard = ((view or {}).get("criteria") or {}).get("hard") or []
    out = [{"item": it, "text": row_text(it, hard), "rejected": False} for it in (view or {}).get("items") or []
           if isinstance(it, dict) and it.get("title") and not _ra.is_lead(it)]
    return out + [{"item": rj, "text": str(rj.get("title")), "rejected": True} for rj in (view or {}).get("rejected") or []
                  if isinstance(rj, dict) and rj.get("title")]


def rows() -> list[dict]:
    """`{"item", "text", "rejected"}` for every row of the recent sheets (candidates and discarded ones)."""
    out: list[dict] = []
    try:
        from widgets.results import data as _d
        names = _d.sheets()
        from nucleo import dispatch as _disp
        live = [str((t or {}).get("sheet") or "").removeprefix("results::") for t in _disp.pending_summaries() or []]
        picked = ([""] if "" in names else []) + [s for s in names if s][-RECENT_SHEETS:]
        for sid in dict.fromkeys(picked + [s for s in live if s and s in names]):
            out += rows_of(_d.view_data(sid) or {})
    except Exception as e:  # noqa: BLE001 — unreadable sheets back nothing: the guard then only cuts what it can see
        emit("row claims: sheets unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return out


def _blocks(window, heard: str):
    for m in [*(window or []), {"role": "user", "content": heard}]:
        if (m or {}).get("role") == "user":
            yield from re.split(r"\n\s*\n", str(m.get("content") or ""))


def his_words(window=None, heard: str = "") -> str:
    """His own words of the window and this turn — without the `[SISTEMA]` notes that ride in his turns."""
    return " ".join(b for b in _blocks(window, heard) if not b.lstrip().startswith("[SISTEMA]"))


def texts(window=None, heard: str = "") -> list[str]:
    """The evidence besides the sheets: the notes pushed into his turns, the in-turn search, the errands' steps.
    His own words are NOT evidence of an attribute — «¿esa es de 8 kilos y clase A?» asks, it does not say."""
    out = [b for b in _blocks(window, heard) if b.lstrip().startswith("[SISTEMA]")]
    try:
        from nucleo.flash import amount_gate as _ag
        out.append(_ag.search_backing())
        from nucleo import dispatch as _disp
        for t in _disp.pending_summaries() or []:
            out.append(" ".join(str((t or {}).get(k) or "") for k in ("phase", "note")))
    except Exception as e:  # noqa: BLE001
        emit("row claims: live sources unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return [t for t in out if t.strip()]


def in_errand(now: float | None = None) -> bool:
    """Is this a shortlist turn — an errand live or just ended, or a results sheet written minutes ago? Outside one,
    «a Netflix plan costs $15.49» is an answer, not a candidate, and the guard stays out (as `amount_gate` does)."""
    import os
    import time
    try:
        from nucleo import dispatch as _disp
        if _disp.pending_summaries() or _disp.recently_ended_sessions():
            return True
        from widgets import store as _store
        now = time.time() if now is None else now
        for name in os.listdir(_store.DATA_DIR):
            f = os.path.join(_store.DATA_DIR, name, "state.json")
            if name.startswith("results") and os.path.exists(f) and now - os.path.getmtime(f) <= SHEET_FRESH_S:
                return True
    except Exception as e:  # noqa: BLE001 — unknown context: stay out, a false cut removes a real delivery
        emit("row claims: errand context unreadable", error=f"{type(e).__name__}: {e}"[:120])
    return False


def goals() -> str:
    """What the live errands were asked — his words, so they back a NAME (never an attribute)."""
    try:
        from nucleo import dispatch as _disp
        return " ".join(str((t or {}).get("request") or "") for t in _disp.pending_summaries() or [])
    except Exception as e:  # noqa: BLE001
        emit("row claims: errands unreadable", error=f"{type(e).__name__}: {e}"[:120])
        return ""


def emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit as _say
        _say("rail", label, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("claim_backing emit failed: %s", e)
