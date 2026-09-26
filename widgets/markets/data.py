"""Markets widget — one price chart (a stock, an index, a currency pair, a crypto).

Built for the operator's demo script (2026-09-26): «Show me a chart of Apple stock today» → «Show me the last
month instead» → «Close the chart». Before it, the agent answered «I can't actually display a chart here».

Data: Yahoo Finance's public chart endpoint (`/v8/finance/chart`), no key. A NAME is resolved to a ticker with
its search endpoint, so «Apple» and «AAPL» land on the same chart. The network lives in `apply_action` only —
`view_data` is the hot path and serves the cache (widgets/AGENTS.md). Stdlib only.

It shows prices and nothing else: no orders, no portfolio, no advice.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import store

WID = "markets"
# A bare «Mozilla/5.0». Measured 2026-09-26: the endpoints answer 429 to a FULL browser user-agent that arrives
# without the site's cookies, and 200 to this one — the opposite of what the house default would suggest.
_UA = "Mozilla/5.0"
_TIMEOUT_S = 3.5              # two calls must fit inside the widget pool's 8 s
_MAX_POINTS = 320

#: range → Yahoo interval. The period names are the ones the operator says; `_range_of` maps his words onto them.
RANGES = {"1d": "5m", "5d": "30m", "1mo": "1d", "3mo": "1d", "6mo": "1d", "1y": "1wk", "5y": "1mo"}
_RANGE_WORDS = (
    (r"\b(today|intraday|day|hoy|d[ií]a)\b", "1d"),
    (r"\b(week|5\s*d(ays)?|semana|5\s*d[ií]as)\b", "5d"),
    (r"\b(3|three|tres)\s*(mo|months?|meses)\b|\bquarter\b|\btrimestre\b", "3mo"),
    (r"\b(6|six|seis)\s*(mo|months?|meses)\b|\bhalf\s*(a\s*)?year\b|\bsemestre\b", "6mo"),
    (r"\b(5|five|cinco)\s*(y|years?|a[nñ]os)\b", "5y"),
    (r"\b(month|30\s*d(ays)?|1\s*mo|mes|[uú]ltimo mes)\b", "1mo"),
    (r"\b(year|12\s*months|1\s*y|a[nñ]o|12\s*meses)\b", "1y"),
)
_TICKER = re.compile(r"^[\^]?[A-Z0-9]{1,6}([.\-=][A-Z0-9]{1,5})?(=X|-USD)?$")


def _seed() -> dict:
    return {"symbol": "", "name": "", "currency": "", "exchange": "", "range": "1d", "points": [],
            "price": None, "change": None, "change_pct": None, "as_of": 0, "fetched_at": 0, "error": ""}


def _load() -> dict:
    return store.load(WID, _seed())


def _get(url: str) -> dict:
    """GET JSON; a 429 on one Yahoo host is retried once on its twin (query1 ↔ query2)."""
    last = None
    for u in (url, url.replace("//query1.", "//query2.") if "//query1." in url else url.replace("//query2.", "//query1.")):
        req = urllib.request.Request(u, headers={"User-Agent": _UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429:
                raise
    raise last


#: The short codes a model writes («1M» measured live, 2026-09-26 — it fell to «today»).
_CODES = {"1m": "1mo", "30d": "1mo", "1month": "1mo", "6m": "6mo", "3m": "3mo", "90d": "3mo", "1q": "3mo",
          "1w": "5d", "7d": "5d", "1wk": "5d", "12m": "1y", "1yr": "1y", "ytd": "1y", "5yr": "5y",
          "today": "1d", "1day": "1d"}


def _range_of(raw) -> str:
    r = str(raw or "").strip().lower()
    if r in RANGES:
        return r
    if r.replace(" ", "") in _CODES:
        return _CODES[r.replace(" ", "")]
    for pat, code in _RANGE_WORDS:
        if re.search(pat, r):
            return code
    return "1d"


def _lookup(query: str) -> tuple[str, str]:
    """(ticker, name) for what the operator said. A ticker-shaped query is taken as it is."""
    q = str(query or "").strip()
    if not q:
        return "", ""
    if _TICKER.match(q.upper()) and (q.isupper() or q.startswith("^") or any(c in q for c in ".-=")):
        return q.upper(), ""
    got = _get("https://query1.finance.yahoo.com/v1/finance/search?"
               + urllib.parse.urlencode({"q": q, "quotesCount": 6, "newsCount": 0}))
    for it in got.get("quotes") or []:
        if str(it.get("quoteType") or "").upper() in ("EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY", "CURRENCY",
                                                       "MUTUALFUND", "FUTURE") and it.get("symbol"):
            return str(it["symbol"]), str(it.get("shortname") or it.get("longname") or "")
    if _TICKER.match(q.upper()):
        return q.upper(), ""
    return "", ""


def _chart(symbol: str, rng: str) -> dict:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='^=-.')}?"
           + urllib.parse.urlencode({"range": rng, "interval": RANGES[rng], "includePrePost": "false"}))
    res = ((_get(url).get("chart") or {}).get("result") or [None])[0]
    if not res:
        raise ValueError("no data for that symbol")
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    pts = [[int(t), round(float(c), 4)] for t, c in zip(ts, closes) if c is not None]
    if len(pts) > _MAX_POINTS:
        step = len(pts) / _MAX_POINTS
        pts = [pts[int(i * step)] for i in range(_MAX_POINTS)] + [pts[-1]]
    price = meta.get("regularMarketPrice")
    price = float(price) if price is not None else (pts[-1][1] if pts else None)
    # «today» compares with yesterday's close; any longer period with where the period started
    base = meta.get("chartPreviousClose") if rng == "1d" else (pts[0][1] if pts else None)
    if rng == "1d" and meta.get("previousClose") is not None:
        base = meta.get("previousClose")
    change = round(price - float(base), 4) if (price is not None and base) else None
    pct = round(change / float(base) * 100, 2) if (change is not None and base) else None
    return {"symbol": str(meta.get("symbol") or symbol), "currency": str(meta.get("currency") or ""),
            "exchange": str(meta.get("fullExchangeName") or meta.get("exchangeName") or ""),
            "name": str(meta.get("shortName") or meta.get("longName") or ""),
            "points": pts, "price": price, "change": change, "change_pct": pct,
            "as_of": int(meta.get("regularMarketTime") or (pts[-1][0] if pts else 0))}


def _summary(db: dict) -> str:
    if not db.get("symbol"):
        return ""
    name = db.get("name") or db["symbol"]
    p, cur, pct = db.get("price"), db.get("currency") or "", db.get("change_pct")
    period = {"1d": "today", "5d": "this week", "1mo": "over the last month", "3mo": "over three months",
              "6mo": "over six months", "1y": "over the last year", "5y": "over five years"}.get(db.get("range"), "")
    move = "" if pct is None else f", {'up' if pct >= 0 else 'down'} {abs(pct):.2f}% {period}"
    when = time.strftime("%a %d %b %H:%M", time.localtime(db["as_of"])) if db.get("as_of") else ""
    return f"{name} ({db['symbol']}) {p:,.2f} {cur}{move}" + (f" — last price {when}" if when else "") \
        if p is not None else f"{name} ({db['symbol']}): no price"


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        return {**{k: db.get(k) for k in _seed()}, "ranges": list(RANGES), "summary": _summary(db)}
    except Exception as e:  # noqa: BLE001 — never raise from the hot path
        return {**_seed(), "ranges": list(RANGES), "summary": "", "error": str(e)[:160]}


def prompt_digest() -> str:
    """What is on screen, so a follow-up («is that good?», «and in euros?») needs no round trip."""
    try:
        s = _summary(_load())
        return f"Markets chart on screen: {s}." if s else ""
    except Exception:  # noqa: BLE001
        return ""


def _fetch_into(db: dict, symbol: str, rng: str, name: str = "") -> dict:
    got = _chart(symbol, rng)
    db.update(got)
    db["name"] = got.get("name") or name or symbol
    db.update({"range": rng, "fetched_at": int(time.time()), "error": ""})
    store.save(WID, db)
    return {"ok": True, "symbol": db["symbol"], "name": db["name"], "price": db["price"],
            "currency": db["currency"], "change_pct": db["change_pct"], "range": rng, "summary": _summary(db)}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()
    try:
        if action == "show":
            query = str(p.get("symbol") or p.get("item") or p.get("query") or "").strip()
            if not query:
                return {"ok": False, "error": "say WHICH stock, index or coin: 'show' needs 'symbol' "
                                              "(a ticker like AAPL or a name like Apple)"}
            sym, name = _lookup(query)
            if not sym:
                return {"ok": False, "error": f"I could not find a market symbol for «{query}» — try its ticker"}
            try:
                return _fetch_into(db, sym, _range_of(p.get("range")), name)
            except Exception:  # noqa: BLE001
                # A NAME that looks like a ticker («NASDAQ», «TESLA», «IBEX») was taken as one and has no
                # chart under that spelling: look it up after all before giving up (V2-773 audit).
                if name or not _TICKER.match(query.upper()):
                    raise
                got = _get("https://query1.finance.yahoo.com/v1/finance/search?"
                           + urllib.parse.urlencode({"q": query, "quotesCount": 6, "newsCount": 0}))
                alt = next((str(it["symbol"]) for it in (got.get("quotes") or [])
                            if it.get("symbol") and str(it["symbol"]).upper() != sym), "")
                if not alt:
                    raise
                return _fetch_into(db, alt, _range_of(p.get("range")),
                                   next((str(it.get("shortname") or it.get("longname") or "")
                                         for it in got.get("quotes") or [] if it.get("symbol") == alt), ""))
        if action in ("range", "refresh"):
            if not db.get("symbol"):
                return {"ok": False, "error": "there is no chart on screen yet — use 'show' with a symbol first"}
            rng = _range_of(p.get("range")) if action == "range" else (db.get("range") or "1d")
            return _fetch_into(db, db["symbol"], rng, db.get("name") or "")
        return {"ok": False, "error": f"unknown action '{action}' — markets has show, range, refresh"}
    except Exception as e:  # noqa: BLE001
        db["error"] = f"{type(e).__name__}: {e}"[:200]
        store.save(WID, db)
        return {"ok": False, "error": f"the price source did not answer ({db['error']}) — try again in a moment"}
