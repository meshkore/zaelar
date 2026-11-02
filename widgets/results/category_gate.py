"""widgets/results/category_gate.py — the sheet's door applies `search.category`: a row that is not one of the things
he asked for never lands as a candidate (V2-782 T3.3).

Every route into the sheet ends at `present`/`append` (`actions.py`), so this is the one place the rule runs: the
listing fast pass, the browser's extraction, a web search's leads and the worker's own report alike. Off rows are
not lost — they go to the REJECTED tab with their reason, and the action's reply tells the worker which and why.

The request side is twofold (see `search.category.asked_from`): `asked`, the operator's own words, stored on the
sheet by whoever opened it for him (`listing_turn`) and grown by every correction that reaches the errand
(`recheck`, wired in `dispatch.inject`); and the sheet's own title, goal and criteria changes.
"""
from __future__ import annotations

from search import asked as _asked
from search import excluded as _excluded
from search import row_fit as _fit

_MAX_ASKED = 900
_HEAD_ASKED = 240            # the commissioning sentence, kept whole when `asked` has to be cut
_MAX_RELAYED = 6
_DEFAULT_TITLES = frozenset(("resultados", "results", "sin resultados", ""))


def _context(data: dict, payload: dict) -> list[str]:
    crit = data.get("criteria") or {}
    pcrit = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    out = [data.get("title"), payload.get("title"), crit.get("goal"), (pcrit or {}).get("goal")]
    out += list(data.get("relayed") or [])          # a correction in OUR words (see `recheck`)
    for src in (crit, pcrit or {}):
        out += list(src.get("changes") or []) + list(src.get("hard") or [])
    # A default title says nothing about what was asked: judging a «Resultados» sheet by category would reject the
    # «funda» of someone who asked for a phone case and whose worker never named the sheet.
    return [str(x) for x in out if x and str(x).strip().lower() not in _DEFAULT_TITLES]


def _own(data: dict, payload: dict) -> str:
    """His words as the sheet knows them: `asked`, plus the corrections a `criteria` op recorded as HIS («correcciones
    del operador» — the turn writes them from his sentence). three-tasks-at-once (ES, 2026-10-11): «27 al menos»
    reached the sheet only as a criteria change, and the gate, reading `asked` alone, never saw it."""
    crit = data.get("criteria") or {}
    pcrit = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    # A change is the TURN's paraphrase of his sentence, so its capitals are the model's style, never his subject:
    # every change joins lower-cased (the subject reader takes titlecase only) and adds only what it states — a
    # spec, a ceiling, a ruled-out word. search-buy-used-car EN (2026-10-14) rejected 55 real cars on «Bay Area»;
    # search-buy-used-car ES (V2-835, 2026-11-02) rejected every non-Flexicar car on «excluir los coches de
    # Flexicar». A subject is HIS words (`asked`) or the brief's declared list; an exclusion is `criteria.excluded`.
    changes = [str(c).lower() for src in (crit, pcrit or {}) for c in (src.get("changes") or [])
               if str(c or "").strip()]
    return " ".join([str(data.get("asked") or "")] + changes).strip()


def _declared(data: dict, payload: dict, key: str = "subjects"):
    """The list the errand DECLARED under `criteria.<key>` — `subjects` (the brief) or `excluded` (whoever recorded
    an exclusion) — or None when nothing declared one."""
    for src in ((payload.get("criteria") if isinstance(payload.get("criteria"), dict) else None),
                data.get("criteria")):
        if isinstance(src, dict) and isinstance(src.get(key), list):
            return [str(s) for s in src[key] if str(s or "").strip()]
    return None


def _ruled_out() -> list[tuple[str, dict]]:
    """The names his STANDING rules rule out of what a sheet shows him (V2-838): the rows of `rules/` active on the
    sheet's request path — `search`, then this card — each with the rule that rules it out. A rule he set in an
    earlier session reaches a search that starts clean, because it is read here, at the door, every time."""
    try:
        import rules
        return rules.excluded(rules.path(surface=rules.SEARCH, widget="results"))
    except Exception as e:  # noqa: BLE001 — an unreadable rules table leaves the sheet's own criteria in charge
        __import__("logging").getLogger(__name__).warning("results: his rules are unreadable (%s)", e)
        return []


def _hay(row: dict) -> str:
    facts = " ".join(f"{f.get('label', '')} {f.get('value', '')}" for f in (row.get("facts") or [])
                     if isinstance(f, dict))
    url = str(row.get("url") or "")
    return _asked.norm(" ".join(str(row.get(k) or "") for k in ("title", "subtitle", "seller", "source"))
                       + f" {facts} {url} " + "".join(c if c.isalnum() else " " for c in url))


def _by_rule(items: list[dict], ruled: list[tuple[str, dict]]) -> tuple[list[dict], list[dict]]:
    """(on, off): a row naming a name his rule rules out is off, and its reason names the RULE, in his words."""
    if not ruled:
        return list(items or []), []
    names = [(_asked.norm(n), r) for n, r in ruled if _asked.norm(n)]
    on, off = [], []
    for it in items or []:
        hay = _hay(it)
        hit = next((r for n, r in names if _excluded.named_in(n, hay)), None)
        if hit is None:
            on.append(it)
            continue
        said = str(hit.get("text") or ", ".join(map(str, hit.get("value") or []))).strip()
        off.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": f"your rule: «{said[:150]}»",
                    "rule": hit.get("id", "")})
    return on, off


def _split(items, own, ctx, data: dict, payload: dict, **kw) -> tuple[list[dict], list[dict]]:
    """Every gate of the door: his standing rules first (their rows name the rule), then the sheet's own request.
    The rule's names also join the declared exclusions, so a name he ruled out is never read as his subject."""
    ruled = _ruled_out()
    on, off_rule = _by_rule(items, ruled)
    declared_out = (_declared(data, payload, "excluded") or []) + [n for n, _r in ruled]
    on, off = _fit.split(on, own, ctx, declared=_declared(data, payload), excluded=declared_out or None, **kw)
    return on, off_rule + off


def _fit_asked(asked: str) -> str:
    """`asked` within `_MAX_ASKED`, keeping its HEAD — the sentence that commissioned the hunt names the subject —
    and its latest corrections; the middle goes. Until 2026-10-16 the last 900 characters were kept, so a long
    round cut off exactly the words the subject reader needs (audit V2-783 P0-1)."""
    if len(asked) <= _MAX_ASKED:
        return asked
    head = asked[:_HEAD_ASKED]
    cut = head.rfind(". ")
    head = head[:cut + 1] if cut >= _HEAD_ASKED // 2 else head
    tail = asked[-(_MAX_ASKED - len(head) - 2):]
    return f"{head} …{tail}"


def keep_asked(data: dict, prev: dict, payload: dict) -> None:
    """`asked` survives a `present` (which rebuilds the sheet) and a payload may set it; so do relayed corrections."""
    asked = str(payload.get("asked") or prev.get("asked") or data.get("asked") or "").strip()
    if asked:
        data["asked"] = _fit_asked(asked)
    if prev.get("relayed") and not data.get("relayed"):
        data["relayed"] = list(prev["relayed"])


def asked_of(sheet: str) -> str:
    """His words as this sheet holds them ("" when none reached it)."""
    from widgets.results import data as _d
    return str(_d.view_data(sheet).get("asked") or "").strip()


def hear(sheet: str, words: str) -> bool:
    """The sentence that COMMISSIONED the errand becomes the sheet's `asked`, when it has none yet. True when set.

    find-concert-tickets ES (2026-10-14): a worker's sheet never had `asked` — only the listing fast pass wrote it —
    so «Rosalía» was nobody's subject, and «Miguel Lago», «El Club de los Poetas Muertos» and «El Cascanueces» were
    offered as Rosalía tickets. Re-judged too: a sheet inherited from a relay may already hold rows."""
    text = " ".join(str(words or "").split())
    if not text or asked_of(sheet):
        return False
    recheck(sheet, text)
    return True


def _file(data: dict, off: list[dict]) -> None:
    cur = list(data.get("rejected") or [])
    seen = {(x.get("url") or x.get("title") or "").strip().lower() for x in cur}
    for r in off:
        r = {**r, "source": "category gate"}            # the reason is ours (English), not the worker's words
        key = (r.get("url") or r.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            cur.append(r)
    from widgets.results import data as _d
    data["rejected"] = cur[:_d._MAX_REJECTED]


def gate(data: dict, items: list[dict], payload: dict, prior=()) -> tuple[list[dict], dict]:
    """(rows that are candidates, extra for the action's reply). Off rows are filed in `data["rejected"]`.
    `prior`: the rows already on the sheet, for an `append` (a second copy of one of them is off)."""
    own, ctx = _own(data, payload), _context(data, payload)
    on, off = _split(items, own, ctx, data, payload, raw_items=payload.get("items"), prior=prior)
    if not off:
        return on, {}
    _file(data, off)
    _emit(len(on), off)
    return on, {"off_category": off[:8],
                "note_for_worker": (f"{len(off)} row(s) are NOT what he asked for — moved to the Rejected tab: "
                                    + "; ".join(f"«{o['title'][:50]}» ({o['why']})" for o in off[:4])
                                    + ". Do not re-add them: present only rows that fit what he asked for.")}


def recheck(sheet: str, correction: str, *, relayed: bool = False) -> int:
    """A correction reached the errand: it joins `asked`, and the rows already on the sheet are judged again.
    Returns how many left the list. Measured (search-buy-used-car ES, 2026-10-11): the worker heard «solo coches,
    no maquetas» and said «lo descarto», yet the eBay rows stayed and the reply kept offering them.

    `relayed`: the text is the MODEL's message to the worker, not his sentence. It joins the context side (what
    was ruled out, the ceiling), never `asked`, whose capitalised names are the subjects every row must name.
    hotel-under-15-days ES (2026-10-14): «DESCARTAR … (Hostel Trotamundos, bambu hostel capsules, Arc House…)» was
    read as his ask, and every real four-star hotel left the sheet for «does not name «hostel trotamundos»»;
    search-buy-guitar ES: «(Wallapop, Milanuncios y similares)» rejected eight guitars the same way."""
    from widgets.results import data as _d
    data = _d.view_data(sheet)
    text = " ".join(str(correction or "").split())
    if text and relayed:
        data["relayed"] = (list(data.get("relayed") or []) + [text[:_MAX_ASKED]])[-_MAX_RELAYED:]
    elif text:
        data["asked"] = _fit_asked((str(data.get("asked") or "") + " " + text).strip())
    own, ctx = _own(data, {}), _context(data, {})
    on, off = _split(data.get("items") or [], own, ctx, data, {})
    if off:
        data["items"] = on
        _file(data, off)
        _emit(len(on), off, why="correction")
    gone, pooled_off = {(o.get("title"), o.get("url")) for o in off}, False
    if data.get("pool"):           # the gathered candidates off the list meet the correction too (V2-835 T2)
        p_on, p_off = _split([r for r in data["pool"] if (r.get("title"), r.get("url")) not in gone], own, ctx,
                             data, {})
        if len(p_on) != len(data["pool"]):
            data["pool"], pooled_off = p_on, True
            _file(data, p_off)
    if text or off or pooled_off:
        _d._save(data, sheet)
    return len(off)


def apply_rules() -> int:
    """A rule of his that rules something out was just written: every sheet that exists meets it now, rows and pool
    alike — the search he is looking at loses what he ruled out without waiting for the next `present`. Returns how
    many rows left the lists."""
    from widgets.results import sheet_names as _names
    return sum(recheck(sheet, "") for sheet in _names.sheets())


def _emit(kept: int, off: list[dict], why: str = "door") -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 off-category rows filed as rejected", role="system",
             extra={"kept": kept, "off": [f"{o['title'][:40]} — {o['why'][:60]}" for o in off[:6]], "why": why})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the sheet
        __import__("logging").getLogger(__name__).debug("category gate emit failed: %s", e)
