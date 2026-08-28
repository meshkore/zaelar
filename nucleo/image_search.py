"""nucleo/image_search.py — finding PICTURES is a different search from finding facts (V2-457).

`websearch` answers a question; this answers "show me". The two look alike and are not: a factual search wants
prose it can synthesise, and a picture search wants a *file* the operator can look at, plus enough provenance
to say where it came from. Running the second through the first is what produced the incident this module was
built from.

WHY IT EXISTS — measured, not assumed. On 2026-08-28 the operator asked for a real photo of the Ferrari Amalfi.
The request escalated to a Brain Worker (the `escalate_to_slowbrain` catalogue named fetching a real photo as a
reason to delegate) and the worker did excellent work for **355 seconds and $1.96**: it confirmed the official
specs, rejected a bot-blocked source and a paywalled one, distrusted a set of URLs it suspected were
hallucinated, and delivered ten verified photos from Autocar India and mad4wheels. It never got Ferrari's own
images, because ferrari.com renders by JS and the worker's fetch saw an empty page.

The same query against Google Images, through the warm Chromium this engine already keeps hot for `websearch`,
answers in **3.0 seconds** with `cdn.ferrari.com` originals, a 3128x2333 Wikimedia master and a 3748x2811
netcarshow press shot. Faster *and* higher-authority — an image index has already done the crawling that the
worker was paying a language model to redo one fetch at a time.

Two things that cost that session most of its time are worth naming, because they are what a dedicated path
removes rather than speeds up:
  * The worker fetched image URLs **through a text model** to check they were valid, and got back prose like
    "this appears to be a valid JPEG file, the data begins with the signature FFD8". Four of those, 3-15s each.
  * It presented twice — eight photos at 202s, then ten at 332s — so the operator waited 3m25s for the first
    picture and another two minutes for two more.

WHAT THIS MODULE IS NOT. It does not decide *whether* a request is a picture request (that is the router's job,
by function-calling, never by a keyword table) and it does not curate. A request that genuinely needs judgement
about which photo is the real one still belongs to a Brain Worker; see `nucleo/flash/image_turn.py` for where
that boundary is drawn and why the fast path is the default rather than the only path.

The parser is deliberately PURE and lives apart from the browser that feeds it: Google's payload shape is the
brittle part, so it is the part that has to be testable without a network. `tests/.../fixtures/` holds a real
recorded payload and the parser is measured against it.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# One result in Google's image payload is a pair of adjacent [url, height, width] triples: the gstatic thumbnail
# first, then the real file. Anchoring on the *pair* is what makes this specific — a lone triple matches dozens
# of unrelated arrays in the same blob, and matching those is how a parser starts returning icons and logos.
_RECORD = re.compile(
    r'\["(https://encrypted-tbn[^"]+?)",(\d{2,5}),(\d{2,5})\]\s*,\s*'
    r'\["(https?://[^"]+?)",(\d{2,5}),(\d{2,5})\]'
)
# Provenance rides just behind each record in two labelled slots. `2000` carries the host and the file weight;
# `2003` carries the page the picture is published on and that page's title. Both are optional by design: a
# result with no attribution is still a usable picture, and dropping it would trade a real answer for a tidy one.
_SITE = re.compile(r'"2000":\[null,"([^"]+)"(?:,"([^"]*)")?')
# The title is a JSON string, so it can legally contain an escaped quote — and it does: one Ferrari result is
# titled `El Ferrari Amalfi, la nueva \"dolce vita\"`. A naive [^"]* stops at the backslash and hands back a
# title ending mid-word with a stray slash, which then gets read aloud. Consume escapes explicitly.
_PAGE = re.compile(r'"2003":\[null,"[^"]*","(https?://[^"]+?)","((?:[^"\\]|\\.)*)"')
# How far behind a record its provenance may sit. Generous enough for the padding Google puts between slots,
# short enough that a result with none of its own cannot borrow the next result's attribution — a wrong source
# is worse than a missing one, because a missing one is visibly missing.
_PROVENANCE_WINDOW = 2000


def _unescape(s: str) -> str:
    """Google's payload is JS source, so its URLs arrive with `=` and `&` written as unicode escapes."""
    return (s.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\u003f", "?")
             .replace("\\u0025", "%").replace("\\/", "/"))


def _title(s: str) -> str:
    """A payload title, unescaped and collapsed. Escaped quotes come back as real ones."""
    t = _unescape(s).replace('\\"', '"').replace("\\'", "'")
    return " ".join(t.split())[:160]


def parse_google_images(blob: str, k: int = 12) -> list[dict]:
    """The image results inside a Google Images page's inline script payload, best first.

    Pure and total: any blob is parseable, an unparseable one is simply empty. It never raises, because the
    caller's fallback for "no pictures" and for "the page shape changed" is the same one, and a crash here would
    take down a turn that could still have degraded to another provider.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in _RECORD.finditer(blob or ""):
        url = _unescape(m.group(4))
        if url in seen:
            continue
        seen.add(url)
        tail = blob[m.end():m.end() + _PROVENANCE_WINDOW]
        site = _SITE.search(tail)
        page = _PAGE.search(tail)
        out.append({
            "url": url,
            "thumb": _unescape(m.group(1)),
            "h": int(m.group(5)), "w": int(m.group(6)),
            "site": site.group(1) if site else "",
            "weight": (site.group(2) or "") if site else "",
            "page": _unescape(page.group(1)) if page else "",
            "title": _title(page.group(2)) if page else "",
        })
        if len(out) >= k:
            break
    return out


# Bing's payload is friendlier — every tile is an <a class="iusc"> whose `m` attribute is a JSON object — but
# its index is the reason it is the FALLBACK and not the default. Measured on the same day with the same query:
# asked for the Ferrari Amalfi it returned an SF90, an F8 Spider, a 12Cilindri and two F80s. Nine of ten
# pictures were a different car. That is not a slower answer, it is a wrong one, and a wrong picture returned
# in 1.5s is worse than no picture — so Bing only runs when Google is blocked, and what it returns is labelled.
_BING = re.compile(r'<a[^>]*class="[^"]*\biusc\b[^"]*"[^>]*\sm="([^"]*)"', re.I)


def parse_yandex_rows(rows: list, k: int = 12) -> list:
    """Normalise the raw tiles Yandex's DOM gives us into the family contract (V2-466).

    PURE on purpose, like its Google sibling: what Yandex hands over is a list of
    `{href, alt, thumb}` read in the page, and the brittle half — pulling the full-size URL out of the
    tile link's `img_url` parameter — is exactly the half that must be testable without a network.

    Yandex earns its place by MEASUREMENT (2026-08-28, same machine, same query): Google answered a
    captcha, Ecosia too, DuckDuckGo and Brave render their gallery only after interaction, and Yandex
    returned 30 usable tiles with the right car. Its known cost is the TITLES, which come back in the
    index's own language (Russian for a Spanish query) — the picture is right, the caption may not be
    readable, and that is why the engine that answered always travels with the result.

    `site` is DERIVED from the image host, the same convention the Bing leg already uses: Yandex does
    not hand the publisher over, and attributing a photo to whoever serves it beats no attribution."""
    out, seen = [], set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        href = str(r.get("href") or "")
        try:
            full = parse_qs(urlparse(href).query).get("img_url", [""])[0]
        except Exception:  # noqa: BLE001
            full = ""
        if not full.startswith("http") or full in seen:
            continue
        seen.add(full)
        thumb = str(r.get("thumb") or "")
        titulo = str(r.get("alt") or "").strip()
        try:
            host = (urlparse(full).netloc or "").lower()
        except Exception:  # noqa: BLE001
            host = ""
        out.append({"url": full, "thumb": thumb if thumb.startswith("http") else full,
                    "title": titulo[:200], "site": host, "page": href,
                    "w": int(r.get("w") or 0), "h": int(r.get("h") or 0)})
        if len(out) >= max(1, int(k or 12)):
            break
    return out


def parse_bing_images(html: str, k: int = 12) -> list[dict]:
    """Same contract as `parse_google_images`, over a Bing Images results page. Pure, total, never raises."""
    import html as _html
    import json as _json
    out: list[dict] = []
    seen: set[str] = set()
    for m in _BING.finditer(html or ""):
        try:
            d = _json.loads(_html.unescape(m.group(1)))
        except Exception:  # noqa: BLE001 — one malformed tile must not lose the other eleven
            continue
        url = str(d.get("murl") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        page = str(d.get("purl") or "")
        out.append({
            "url": url, "thumb": str(d.get("turl") or ""), "h": 0, "w": 0,
            "site": _host(page), "weight": "",
            "page": page, "title": " ".join(str(d.get("t") or "").split())[:160],
        })
        if len(out) >= k:
            break
    return out


def _host(url: str) -> str:
    """The host of a URL, or "" — used to attribute a picture whose provider gave no site of its own."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or ""
    except Exception:  # noqa: BLE001
        return ""
