"""search/result.py — the ONE shape every search door returns (V2-782 T1.3).

Before this module the engine had five doors into the results sheet and five row shapes: a web search wrote
`{title, subtitle, url, facts:[Origen]}` (`workers/findings.hand_search_rows`), the listing pass wrote
`{title, subtitle, price, url, image, facts}` (`flash/listing_turn._to_row`), the browser wrote
`{title, price, url, image, tel}` (`results/intake._to_item`), a MeshKore agent wrote `{title, price, url}`
(`mesh_cli._rows_in`) and the worker's own `present` wrote whatever it liked. None of them said WHAT the row
was — a candidate the operator can act on, or the page that lists candidates — and none carried the criterion
the operator had asked for, so a sheet full of «Las 10 mejores empresas de alquiler…» was presented as rental
cars (measured 2026-10-10, see the initiative §1).

The contract, in one sentence: **a result is a list of CANDIDATES, each naming one thing with a datum of its
own, plus the PAGES that were not candidates (kept, with the reason), plus the SOURCES tried, plus the
CRITERIA the search was asked for and which of them NO row could show.** Every door returns this; the sheet
writes `rows()`; the turn reads `answer`, `candidates` and `unshown`; the worker reads `needs`.

Prices, ratings and phones travel AS THE SOURCE WROTE THEM («159,00 €», «4,6/5», «+34 …»). Normalising is the
reader's job and converting a currency silently is the boat use case's forbidden move (V2-556).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

#: The modules a request can be routed to. Closed vocabulary — `route.py` chooses among these, nothing else.
INLINE_FACT = "inline_fact"
LISTING = "listing"
LOCAL_SERVICE = "local_service"
IMAGES = "images"
BROWSER = "browser"
BRAIN_WORKER = "brain_worker"
MODULES = (INLINE_FACT, LISTING, LOCAL_SERVICE, IMAGES, BROWSER, BRAIN_WORKER)

#: Where a row came from. Closed too: a reader that wants to treat a web LEAD differently from an extracted
#: LISTING (V2-376) reads this field, never the wording of a fact.
ORIGINS = ("web", "listing", "local", "browser", "mesh", "images", "worker")


def _labels() -> dict:
    """The sheet's fact labels in the engine's language. The sheet shows them to the operator, so they are
    product text (i18n), not vocabulary — `candidacy` reads them in BOTH languages regardless."""
    try:
        from i18n import langs as _langs
        es = (_langs.current_code() or "es").lower() == "es"
    except Exception:  # noqa: BLE001 — a row must never fail to build because the language is unreadable
        es = True
    if es:
        return {"origin": "Origen", "phone": "Teléfono", "rating": "Valoración", "availability": "Disponibilidad"}
    return {"origin": "Origin", "phone": "Phone", "rating": "Rating", "availability": "Availability"}


#: What each origin says in the Origin fact — the value `hand_search_rows` has written since V2-376, kept so the
#: rows already on operators' sheets and the new ones read the same.
_ORIGIN_VALUES = {"es": {"web": "búsqueda web", "listing": "anuncio", "local": "directorio", "browser": "navegador",
                         "mesh": "agente de la red", "images": "imágenes", "worker": "worker"},
                  "en": {"web": "web search", "listing": "listing", "local": "directory", "browser": "browser",
                         "mesh": "network agent", "images": "images", "worker": "worker"}}


@dataclass
class Candidate:
    """ONE thing the operator could act on, with at least one datum of its own."""
    title: str
    url: str = ""
    subtitle: str = ""
    price: str = ""
    rating: str = ""
    phone: str = ""
    availability: str = ""
    image: str = ""
    origin: str = ""
    facts: list = field(default_factory=list)

    def to_row(self) -> dict:
        """The sheet's closed item schema (`widgets/results/data._ITEM_FIELDS`). Phone, rating, availability and
        origin travel as FACTS because the schema has no field for them — the way the phone has travelled since
        V2-240 — so the sheet contract does not change and `candidacy` can still read them back."""
        lab = _labels()
        row: dict = {"title": str(self.title or "").strip()[:300]}
        for k in ("subtitle", "price", "url", "image"):
            v = str(getattr(self, k) or "").strip()
            if v:
                row[k] = v
        facts: list[dict] = []
        if self.phone:
            facts.append({"label": lab["phone"], "value": str(self.phone)[:40]})
        if self.rating:
            facts.append({"label": lab["rating"], "value": str(self.rating)[:40]})
        if self.availability:
            facts.append({"label": lab["availability"], "value": str(self.availability)[:60]})
        facts.extend(f for f in (self.facts or []) if isinstance(f, dict) and f.get("label"))
        if self.origin:
            code = "es" if lab["origin"] == "Origen" else "en"
            facts.append({"label": lab["origin"], "value": _ORIGIN_VALUES[code].get(self.origin, self.origin)})
        if facts:
            row["facts"] = facts[:8]
        return row


@dataclass
class Page:
    """A page that LISTS or DISCUSSES candidates — a ranking, an article, a policy page. Never counted as a
    result; kept one click away in the Sources tab with the reason, so a worker opens it instead of presenting it."""
    title: str
    url: str = ""
    why: str = ""

    def to_source(self) -> "Source":
        return Source(name=self.title, url=self.url, status="page", note=self.why)


@dataclass
class Source:
    """One door tried: a provider, a fetched host, a page filed as not-a-candidate."""
    name: str
    url: str = ""
    status: str = "ok"      # ok · blocked · error · empty · page
    note: str = ""
    found: int | None = None

    def to_row(self) -> dict:
        row: dict = {"name": str(self.name or "")[:160], "status": self.status}
        if self.url:
            row["url"] = str(self.url)[:500]
        if self.note:
            row["detail" if self.status == "page" else "note"] = str(self.note)[:200]
        if self.found is not None:
            row["found"] = int(self.found)
        return row


@dataclass
class SearchResult:
    """What `search.find()` returns, whichever module ran."""
    query: str
    route: str = ""
    provider: str = ""
    answer: str = ""
    candidates: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    criteria: dict = field(default_factory=dict)
    unshown: list = field(default_factory=list)
    needs: str = ""            # "" · browser · brain_worker — what the service could not do by itself
    failure: dict | None = None
    took_ms: int = 0
    repeated: dict | None = None
    raw: dict | None = None      # the chain's own dict (fact / leads), for callers that still read that shape

    def ok(self) -> bool:
        return bool(self.candidates or self.answer)

    def rows(self) -> list[dict]:
        return [c.to_row() for c in self.candidates]

    def source_rows(self) -> list[dict]:
        return [s.to_row() for s in self.sources] + [p.to_source().to_row() for p in self.pages]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        d["ok"] = self.ok()
        d["n"] = len(self.candidates)
        return d


def candidate_from_row(row: dict, origin: str = "") -> Candidate:
    """A sheet-shaped row (any door's) → a Candidate. Phone/rating/availability are read back from the facts in
    either language; unknown facts are kept as facts."""
    facts = [f for f in (row.get("facts") or []) if isinstance(f, dict)]
    keep: list[dict] = []
    phone = str(row.get("tel") or row.get("phone") or "")
    rating = str(row.get("rating") or row.get("score") or "")
    avail = str(row.get("availability") or "")
    found_origin = origin
    for f in facts:
        lab = str(f.get("label") or "").strip().lower()
        val = str(f.get("value") or "").strip()
        if lab.startswith(("tel", "phone")) and not phone:
            phone = val
        elif lab in ("valoración", "valoracion", "rating", "score", "puntuación", "puntuacion") and not rating:
            rating = val
        elif lab in ("disponibilidad", "availability") and not avail:
            avail = val
        elif lab in ("origen", "origin", "fuente", "source"):
            found_origin = found_origin or _origin_code(val)
        else:
            keep.append(f)
    return Candidate(title=str(row.get("title") or "").strip(), url=str(row.get("url") or "").strip(),
                     subtitle=str(row.get("subtitle") or "").strip(), price=str(row.get("price") or "").strip(),
                     rating=rating, phone=phone, availability=avail, image=str(row.get("image") or "").strip(),
                     origin=found_origin, facts=keep)


def _origin_code(value: str) -> str:
    low = str(value or "").strip().lower()
    for code in ("es", "en"):
        for k, v in _ORIGIN_VALUES[code].items():
            if v == low:
                return k
    return ""
