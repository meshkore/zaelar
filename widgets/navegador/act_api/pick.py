"""Ordering the rows of an extracted page: by identity (a name), by amount, without the template boilerplate every
row shares, and without repeated URLs. Names are read through the package (`_f.<name>`).
"""

from widgets.navegador import act_api as _f


def by_identity(items) -> tuple:
    """Split the extracted items into (NAMED, UNNAMED), preserving relative order within each half.

    A row without a title is navigation chrome (category link, price filter) and comes BEFORE the product cards in
    DOM order on any listing. It is a PARTITION by a structural fact, not a ranking nor a pattern blacklist:
    nothing is judged (that is the brain's) and nothing is dropped — the unnamed half is counted and reported.
    """
    named, unnamed = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        (named if str(it.get("title") or "").strip() else unnamed).append(it)
    # V2-346 — a name several rows share as a TEMPLATE is nobody's identity (the `cardWalk` rule lifted to rows,
    # see `_boilerplate_prefix`): those rows join the unnamed group, counted and reported.
    if named:
        _tpl = _f._boilerplate_prefix([str(it.get("title") or "").strip() for it in named])
        if _tpl:
            _keep, _cromo = [], []
            for it in named:
                t = str(it.get("title") or "").strip()
                (_cromo if t.startswith(_tpl) and len(t) > len(_tpl) else _keep).append(it)
            named, unnamed = _keep, unnamed + _cromo
    # V2-375 — the same rule from the other end: a TAIL every title carries is trimmed and the row KEPT, because
    # its identity is intact in front (with a shared prefix the row has none and is degraded instead).
    if named:
        _cola = _f._boilerplate_suffix([str(it.get("title") or "").strip() for it in named])
        if _cola:
            for it in named:
                t = str(it.get("title") or "").strip()
                if t.endswith(_cola) and len(t) > len(_cola):
                    it["title"] = t[: -len(_cola)].rstrip(" -–—·|,;:")
    return named, unnamed


def _boilerplate_suffix(titles: list) -> str:
    """The suffix shared by at least HALF the titles (and never fewer than three), or «» if there is none.

    Twin of `_boilerplate_prefix` with its same two brakes (minimum length, half the rows). Implemented by
    reversing the strings and reusing the same finder, so the thresholds can never drift apart.
    """
    return _f._boilerplate_prefix([t[::-1] for t in titles if t])[::-1]


def _boilerplate_prefix(titles: list) -> str:
    """The prefix shared by at least HALF the titles (and never fewer than three), or «» if there is none.

    Prefix, not equality, because that is how a template comes (links differing only in a final parenthesis). The
    caller requires each row to add something after it: identical titles are the same product in several shops,
    where the name does identify the thing. On a sorted list each window of the minimum size suffices.
    """
    ts = sorted(t for t in titles if t)
    n = len(ts)
    k = max(_f._TPL_MIN_ROWS, (n + 1) // 2)
    if n < k:
        return ""
    best = ""
    for i in range(0, n - k + 1):
        a, b = ts[i], ts[i + k - 1]
        j = 0
        while j < min(len(a), len(b)) and a[j] == b[j]:
            j += 1
        if j > len(best):
            best = a[:j]
    return best if len(best) >= _f._TPL_MIN_CHARS else ""


def by_amount(items) -> tuple:
    """Split NAMED rows into (rows you can act on, hollow ones), keeping the relative order inside each half.

    Sibling of `by_identity`, one layer deeper: «does it carry anything to act on?» — a real amount or a phone.
    A named row with neither must not take one of the slots the note offers. Any digit other than zero is an
    amount (no locale needed; «169 00 €» still counts); a ZERO is not a price. A PARTITION, nothing dropped; on a
    directory with no prices one half is empty and the order is unchanged. A phone counts as much as an amount
    (V2-240: a result is a name and a way to act on it).
    """
    withs, hollow = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        digits = "".join(c for c in str(it.get("price") or "") if c.isdigit())
        actionable = any(c != "0" for c in digits) or bool(str(it.get("tel") or "").strip())
        (withs if actionable else hollow).append(it)
    return withs, hollow


def dedupe_by_url(items) -> tuple:
    """The SAME URL is not two findings. Return (deduplicated list, number collapsed).

    Repeats would take the note's slots to say the same thing. Two rows with the same address are the same page
    (not interpretation); the FIRST occurrence is kept, and a row WITHOUT url is never deduplicated against anything.
    """
    out, seen, dropped = [], set(), 0
    for it in (items or []):
        u = str((it or {}).get("url") or "").strip()
        if u and u in seen:
            dropped += 1
            continue
        if u:
            seen.add(u)
        out.append(it)
    return out, dropped
