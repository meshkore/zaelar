"""search/candidacy.py — is this row a CANDIDATE, or the PAGE that lists candidates? (V2-782 T3.2)

Measured 2026-10-10 (best-rated-rental-car, cheapest-monitor, compare-insurance-quotes, ES and EN): every door
into the sheet — the web-search door (`nucleo.workers.findings.hand_search_rows`), the browser extraction
(`results/intake.push`) and the worker's own `present` — let pages in as results. «Las 10 mejores empresas de…»,
«TOP 35 Compañías…», «The 6 Best Budget Monitors – RTINGS», mapfre's «Política de Privacidad» carrying the
site's phone number. The sheet showed them as candidates, the turn read them out as candidates, and the
operator never got one real offer. The doors differ; the place they all end is `present`/`append`, so the
rule lives here, once, and the service applies it before anything reaches the sheet.

THE RULE. A candidate names one thing and carries a DATUM of its own — a price, a score, a fact, a phone that
is not the whole site's — or at least a way to act on it. A row WITHOUT a datum is a page when its structure
says so: its url path is an article / ranking / help / policy page, or its title counts or ranks a category
(«10 best…», «TOP 35…», «The best …»). A policy/account page (privacy, cookies, terms, disclosures, login) is
never a candidate, whatever amount an extractor grabbed from it. A web-search lead whose title counts a
category is a ranking even if its snippet carried a price: that price is one of ten, not the page's.

A phone shared by rows with different titles is the SITE's switchboard (mapfre's footer, measured), so it
does not count as a datum; distinct phones on one host (Google Maps plumbers) each do.

Pages are not dropped: they become SOURCES (the sheet's Sources tab), with the reason, and the caller's
reply names them so the worker knows to open them instead of presenting them.

The token sets below are the only vocabulary, and it is URL/title STRUCTURE, not intent: path segments and
ranking words in ES and EN. Keep them small; a word belongs here only if a row measured carrying it was a
page. Tested in `tests/search/unit/test_a_page_is_a_source_not_a_candidate.py` against recorded sheets.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

#: Path tokens of a page that LISTS or DISCUSSES things (an article, a ranking, a help page).
_LISTING_TOKENS = frozenset((
    "best", "mejores", "top", "ranking", "picks", "blog", "articulos", "articles", "article", "news",
    "noticias", "guia", "guide", "faq", "faqs", "contacto", "contact", "comparativa", "comparison", "review",
    "reviews", "opiniones",
))
#: Path tokens of a page that is never an offer: policy, legal, account.
_POLICY_TOKENS = frozenset((
    "privacidad", "privacy", "cookies", "legal", "terms", "terminos", "disclosures", "licenses", "login",
    "signin", "aviso",
))
#: A title that COUNTS a category: «10 mejores…», «The 6 Best…», «TOP 35…», «7 Cheapest…».
_COUNTED = re.compile(r"\b\d{1,3}\s+(?:best|top|cheapest|mejores|mejor|baratos|baratas|compañías|companias|empresas"
                      r"|opciones|options)\b|\btop\s*\d{1,3}\b", re.IGNORECASE)
#: A title that RANKS a category without a count: «The Best Computer Monitors…», «Los mejores…».
_RANKED = re.compile(r"^\s*(?:the\s+|los\s+|las\s+|el\s+|la\s+)?(?:best|mejores|mejor|cheapest|top)\b", re.IGNORECASE)
_ORIGIN_LABELS = ("origen", "origin", "fuente", "source")
_WEB_LEAD_VALUES = ("búsqueda web", "busqueda web", "web search", "web")


#: A monetary amount as sources write one: $1,299.99 · 199,99 € · €249 · USD 249 · 249 USD · £99 (V2-471).
_AMOUNT_RE = re.compile(
    r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|€)|(?:USD|EUR|GBP)\s?\d[\d.,]*|\d[\d.,]*\s?(?:USD|EUR|GBP))", re.I)


def lone_amount(text: str) -> str:
    """The ONE amount `text` names, or "" when it names none — or several: picking one of «was $399 now $279»
    would be inventing a datum with the shape of an observation (V2-471)."""
    hits = [h.strip() for h in _AMOUNT_RE.findall(str(text or ""))]
    return hits[0][:20] if len(hits) == 1 else ""


def _digits(v) -> str:
    return re.sub(r"\D", "", str(v or ""))[-9:]


def _is_phone(label: str) -> bool:
    lab = label.strip().lower()
    return lab.startswith("tel") or lab.startswith("phone")


def _path_tokens(url: str) -> set[str]:
    try:
        path = urlparse(str(url or "")).path.lower()
    except ValueError:
        return set()
    return {t for t in re.split(r"[/\-_.]+", path) if t}


def _shared_phones(rows: list[dict]) -> set[str]:
    """Phones that appear under two or more different titles in this batch (plus what the sheet holds)."""
    seen: dict[str, set[str]] = {}
    for r in rows:
        for f in (r.get("facts") or []):
            if isinstance(f, dict) and _is_phone(str(f.get("label") or "")):
                d = _digits(f.get("value"))
                if len(d) >= 6:
                    seen.setdefault(d, set()).add(str(r.get("title") or "").strip().lower())
    return {d for d, titles in seen.items() if len(titles) > 1}


def _has_datum(row: dict, shared: set[str]) -> bool:
    if row.get("price") or row.get("score") or row.get("parts") or row.get("lines"):
        return True
    for f in (row.get("facts") or []):
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or "")
        if label.strip().lower() in _ORIGIN_LABELS:
            continue
        if _is_phone(label) and _digits(f.get("value")) in shared:
            continue
        if str(f.get("value") or "").strip():
            return True
    return False


def _is_web_lead(row: dict) -> bool:
    if str(row.get("origin") or "").lower() == "web":
        return True
    return any(isinstance(f, dict) and str(f.get("label") or "").strip().lower() in _ORIGIN_LABELS
               and str(f.get("value") or "").strip().lower() in _WEB_LEAD_VALUES for f in (row.get("facts") or []))


def why_a_page(row: dict, shared: set[str] = frozenset()) -> str:
    """The reason this row is a PAGE and not a candidate, or "" when it is a candidate."""
    title = str(row.get("title") or "")
    tokens = _path_tokens(row.get("url") or "")
    if tokens & _POLICY_TOKENS:
        return "a policy or account page, never an offer"
    counted = bool(_COUNTED.search(title))
    if counted and _is_web_lead(row):
        return "a ranking article (its title counts the category)"
    if _has_datum(row, shared):
        return ""
    if counted or _RANKED.search(title):
        return "a ranking article (its title ranks the category), no datum of one candidate"
    if tokens & _LISTING_TOKENS:
        return "an article, ranking or help page (its url), no datum of one candidate"
    return ""


def split(items: list[dict], prior: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """(candidates, pages). `pages` carry `why`; `prior` is what the sheet already holds (for shared phones)."""
    shared = _shared_phones(list(prior or []) + list(items or []))
    keep, pages = [], []
    for it in items or []:
        why = why_a_page(it, shared)
        if why:
            pages.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why})
        else:
            keep.append(it)
    return keep, pages


def as_sources(pages: list[dict]) -> list[dict]:
    """The pages, in the Sources tab's shape: still one click away, no longer counted as results."""
    return [{"name": p["title"], "url": p.get("url") or "", "status": "ok", "detail": "page, not a candidate: "
             + p["why"]} for p in pages]


def note_for_worker(pages: list[dict], kept: int) -> str:
    if not pages:
        return ""
    head = (f"{len(pages)} row(s) are PAGES, not candidates — moved to the Sources tab: "
            + "; ".join(f"«{p['title'][:50]}» ({p['why']})" for p in pages[:4]))
    tail = (" Open them and present the entries they list, each with its own price/rating/phone."
            if kept else " The sheet has NO candidate yet: say so, and open those pages for real entries.")
    return head + "." + tail


def unshown_criteria(items: list[dict], criteria: dict) -> list[str]:
    """The hard criteria when NO candidate carries any datum at all: nothing on the sheet can show them met.

    Structural on purpose: whether a «Rating» fact answers «best-rated» is the model's reading; that the rows
    carry NOTHING but a name and a link is a fact, and presenting them as meeting a criterion is the lie."""
    crit = [str(c) for c in ((criteria or {}).get("hard") or []) + ((criteria or {}).get("quality_bar") or [])]
    if not crit or not items:
        return []
    shared = _shared_phones(items)
    if any(_has_datum(i, shared) for i in items):
        return []
    return crit[:6]
