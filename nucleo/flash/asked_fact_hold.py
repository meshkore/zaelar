"""nucleo/flash/asked_fact_hold.py — a row that does not carry what he asked about is not owed to him yet.

search-buy-vinyl EN (2026-10-14). «Find me an original pressing of 'The Dark Side of the Moon' in good condition for
under $70.» Then «are any of them actually original pressings? and what condition are they in», «no need to show it
again, just let me know when you have the pressing and condition details», and «can't tell if it works without
knowing if it's an original pressing». Three times the delivery backstop glued «Actually, there are already
candidates on the results sheet: …» to the reply — rows carrying a title and a price and nothing about pressing or
condition — once in the very sentence where the model had promised «I won't push the sheet on you again».

What he asked about is read from his own words, never from a word list: the stems (six letters or more) of what he
said AFTER the commission that are stems of the commission itself — his requirements, said again. A row carries one
when its title names it or a fact of the row VERIFIES it (`hard_checks.status` yes/no: a «?» or a source stamp is not
an answer). Until a row carries at least half of them, it is not news to him, so the tail does not offer it and a
finished shortlist does not name it. With nothing asked, nothing changes.
"""
from __future__ import annotations

import re

from search.asked import norm as _norm

#: Shorter words are function words in both product languages ("under", "about"): no requirement of his.
_MIN_LETTERS = 6
_STEM = 6


def _stems(text) -> set[str]:
    return {w[:_STEM] for w in re.findall(r"[a-z]{%d,}" % _MIN_LETTERS, _norm(text))}


def asked(commission: str, said) -> set[str]:
    """The requirements of `commission` that his LATER sentences asked about again. `said` is his sentences in
    order; the first one that names a requirement is the commission being made (a listing errand's request is our
    query, not his words), so it asks nothing new — and neither does the commission's own text."""
    want = _stems(commission)
    out: set[str] = set()
    if not want:
        return out
    first = True
    for s in said or []:
        got = _stems(s) & want
        if not got:
            continue
        if first or _norm(s) == _norm(commission):
            first = False
            continue
        out |= got
    return out


def his_sentences(window, heard_now: str = "") -> list[str]:
    """His turns in the conversation window, in order, with this turn's words last."""
    out = [str((m or {}).get("content") or "") for m in (window or []) if (m or {}).get("role") == "user"]
    if heard_now and (not out or out[-1].strip() != str(heard_now).strip()):
        out.append(str(heard_now))
    return out


def recent_his_sentences(limit: int = 12) -> list[str]:
    """His recent turns from the conversation memory, oldest first — both channels write it. [] when unreadable."""
    try:
        from memory import api as _mem
        return his_sentences(_mem.recent_window(limit=limit, max_chars=4000) or [])
    except Exception as e:  # noqa: BLE001 — without a window nothing is held
        __import__("logging").getLogger(__name__).debug("asked_fact_hold: window unreadable: %s", e)
        return []


def carries(item: dict, want: set[str]) -> bool:
    """Does this sheet row answer at least half of what he asked about?"""
    if not want:
        return True
    from widgets.results import hard_checks as H
    have = _stems((item or {}).get("title"))
    for f in (item or {}).get("facts") or []:
        if isinstance(f, dict) and H.status(f.get("value"))[0] in (H.YES, H.NO):
            have |= _stems(f.get("label")) | _stems(f.get("value"))
    return 2 * len(want & have) >= len(want)


def _items() -> list[dict]:
    """The named rows of every live errand's own sheet — where a delivered «title — price» comes from."""
    from nucleo import dispatch as _disp
    from widgets.results import data as _sheet
    out: list[dict] = []
    for t in _disp.pending_summaries() or []:
        if t.get("sheet"):
            out += [i for i in ((_sheet.view_data(str(t["sheet"])) or {}).get("items") or [])
                    if isinstance(i, dict) and str(i.get("title") or "").strip()]
    return out


def rows_owed(goal: str, rows: list[str], said, items: list[dict] | None = None) -> list[str]:
    """`rows` («title — price» strings) without the ones that do not carry what he asked about. Never raises."""
    try:
        want = asked(goal, said)
        if not want or not rows:
            return list(rows or [])
        by_title = {_norm(i.get("title")): i for i in (_items() if items is None else items)}
        # a row whose sheet entry cannot be found is kept: what cannot be read is not judged
        kept = [r for r in rows if (k := _norm(str(r).split(" — ")[0])) not in by_title or carries(by_title[k], want)]
        if len(kept) < len(rows):
            _emit("🤐 delivery backstop held: rows lack what he asked about", held=len(rows) - len(kept),
                  asked=sorted(want)[:6], goal=str(goal or "")[:80])
        return kept
    except Exception as e:  # noqa: BLE001 — a reader that fails leaves the rows as they were
        __import__("logging").getLogger(__name__).warning("asked_fact_hold failed: %s", e)
        return list(rows or [])


def items_owed(goal: str, items: list[dict], said) -> list[dict]:
    """Sheet rows (dicts) that carry what he asked about — the shortlist's version of `rows_owed`."""
    want = asked(goal, said)
    return [i for i in items or [] if carries(i, want)]


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("asked_fact_hold emit failed: %s", e)
