"""
observability.evidence — store EVIDENCE of what the outside world returned, within a budget.

Until 2026-08-10 the record captured the QUESTION and the DECISION, not the PROOF: from a search it retained the
provider, result count, and latency, but **not which pages came back or what they said**; from a Brain Worker
step it retained the tool and its target (the query, the URL), **not what it answered**. With that, one can audit
that the system SEARCHED, but not whether it searched WELL: the question that matters —“do the results support
what it answered?”— was unverifiable after the fact.

The format lives here and, above all, **the budget**. The evidence goes inside the event payload (same row, same
writer, same lifetime), so without a cap a single search with ten long snippets could weigh more than the rest of
the turn combined. Rules:

- **Trim, do not summarize.** A summary is an interpretation; an audit needs the text as-is, even if it is only
  the beginning. Every trim leaves a visible mark (`…`).
- **Headers before bodies.** A web result ALWAYS retains its title and URL (what identifies the source and allows
  returning to it), and the snippet is trimmed aggressively.
- **One cap per event, not per field.** `TOTAL` bounds the entire evidence for one row; if ten results do not
  fit, the first ones are included and the number left out (`omitted`) is stated — the information that there
  were more is never silently lost.
"""
from __future__ import annotations

MAX_ITEMS = 8            # results per event: the first ones are what the model actually reads
MAX_SNIPPET = 220        # body of each result
MAX_TITLE = 120
MAX_URL = 300            # a marketplace URL with parameters is legitimately long
MAX_BODY = 1500          # tool response / page extract
TOTAL = 6000             # evidence ceiling for ONE event


def clip(s, n: int) -> str:
    """Trim to `n`, marking the cut. Never raises: evidence is best-effort and must never bring down the emitter."""
    try:
        t = " ".join(str(s or "").split())
    except Exception:
        return ""
    return t if len(t) <= n else t[: n - 1] + "…"


def web_results(results, max_items: int = MAX_ITEMS) -> dict:
    """`[{title,snippet,url}]` → `{items:[{t,u,s}], omitted:N}` within a budget.

    Short keys on purpose (`t`/`u`/`s`): this is repeated per result and per event, and the payload goes into a
    JSON column read millions of times — the long name is not paid for in every row."""
    items, used = [], 0
    src = list(results or [])
    for r in src[:max_items]:
        if not isinstance(r, dict):
            continue
        it = {"t": clip(r.get("title"), MAX_TITLE), "u": clip(r.get("url"), MAX_URL)}
        sn = clip(r.get("snippet"), MAX_SNIPPET)
        if sn:
            it["s"] = sn
        cost = len(it.get("t", "")) + len(it.get("u", "")) + len(it.get("s", ""))
        if used + cost > TOTAL:
            break                            # the ceiling rules: 5 complete results are better than 8 mangled ones
        used += cost
        items.append(it)
    return {"items": items, "omitted": max(0, len(src) - len(items))}


def body(text) -> str:
    """The body of an external response (tool result, page extract, API error)."""
    return clip(text, MAX_BODY)
