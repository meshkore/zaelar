"""search/web.py — WEB SEARCH for facts and leads, the provider CHAIN (V2-022; moved from `nucleo/websearch.py`
by V2-782, which keeps that name as an alias so every caller and test still works).

**Model-agnostic** search capability (we do not depend on the model having native search — Grok/GLM/Z.AI do not;
Claude Code does): an internal primitive that any part of the system can call.

THREE "search" modes, which must NOT be confused:
  1. **Direct fact + SYNTHESIS** (this module) — "¿quién ganó el partido?", the weather, a price, a forecast.
     Lightweight route; FlashBrain uses it through the `web_search` tool, resolved WITHIN the turn; SlowBrain uses it
     to feed reports with current data. Quality comes first: if an **AI-answer** provider exists (Perplexity / Tavily /
     Brave summarizer / Gemini grounding), the answer arrives ALREADY synthesized and cited; otherwise we fall back to
     raw snippets (DuckDuckGo/Brave) and the brain synthesizes them with the model already paid for the turn.
  2. **Web / marketplace navigation** (Amazon, Wallapop…) — this is NOT it: no search engine returns that data;
     you must ENTER and browse. The **browser** does it (`widgets/navegador/`, `automate_web`, SlowBrain).
  3. **Deep research / report** (a study with lots of current data) — SlowBrain (CodeAgent) with native
     `WebSearch`/`WebFetch` (Claude Code) and/or this primitive in a loop; synthesis happens in the agent itself.

LAYERED DESIGN (quality first, cost second; auto-upgrade by key):
  - Provider order: **AI answer** (Perplexity → Tavily, if keyed) → **snippets** (Brave, if keyed) →
    **free** (DuckDuckGo HTML, no key, always available). Explicit override with `WEBSEARCH_PROVIDER`.
  - ALWAYS outside the event loop (the caller uses `asyncio.to_thread`): this is blocking network I/O.
  - Fail-open: on error, degrade to the next provider; if everything fails, empty — the brain says so, never crashes.

Keys (env / `.meshkore/credentials/zaelar.env`, manageable through the UI later):
  `PERPLEXITY_API_KEY` · `TAVILY_API_KEY` · `BRAVE_SEARCH_KEY`. With none → works for free with DuckDuckGo.
"""
from __future__ import annotations

import html as _html
import os
import re as _re
import time as _time
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger
from nucleo.errors import brief as _brief

from . import hooks as _hooks
from .providers import keys as _keys
from .providers import paid as _paid_providers

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0"))
_MAX_RESULTS = 5


# ── keys / provider selection ────────────────────────────────────────────────────────────────────────────
# Through `providers.keys.key`, the one door every paid index's key passes (and where the energy lease says no).
def perplexity_key() -> str: return _keys.key("perplexity")
def tavily_key() -> str: return _keys.key("tavily")
def brave_key() -> str: return _keys.key("brave")


def _google_on() -> bool:
    """The FREE Google-via-browser layer (V2-024). ON unless BROWSER_SEARCH=0."""
    try:
        from search import browser as browser_search
        return browser_search.enabled()
    except Exception:
        return False


#: The chain for a FACT (an answer the turn speaks), CHEAPEST that answers first (2026-10-23). Measured on twelve
#: ES/EN fact questions: the warm Chromium (`google`) brought the datum in its snippets 12/12 in 1.2-2 s at no
#: cost; Gemini grounding answers as well as OpenAI and is free within its daily quota; Z.ai returns good pages at
#: about $0.01 a call; OpenAI wrote the best answers at about $0.025 a call — so it is the paid rung that does not
#: fail, not the one asked every time. The fast model composes the reply from snippets in the same pass it uses
#: for a synthesised answer, so a snippet-only rung adds no trip. A rung that refuses for a lasting reason
#: (quota, captcha, key) is set aside for a window (`_set_aside_if_lasting`), so a blocked Chromium is not paid
#: for on every search. Unkeyed today and kept for whoever holds their keys: perplexity, tavily, brave.
_ANSWER_ORDER = ("google", "gemini", "zai", "perplexity", "tavily", "brave", "openai", "ddg")
#: The chain for LEADS (pages to open: listing discovery, a local service): providers that return real urls.
#: Perplexity and Gemini are skipped — their citations are redirects or domains, useless as pages to fetch.
_RESULTS_ORDER = ("zai", "brave", "openai", "tavily", "google", "ddg")


def provider(mode: str = "answer") -> str:
    """Active provider: the first usable rung of the mode's chain (a fact: cheapest first; leads: real pages first).
    Override with WEBSEARCH_PROVIDER (perplexity|tavily|openai|gemini|zai|brave|google|ddg). DDG is the last resort."""
    forced = (os.getenv("WEBSEARCH_PROVIDER") or "").strip().lower()
    if forced:
        return forced
    for src in (_RESULTS_ORDER if mode == "results" else _ANSWER_ORDER):
        if _usable(src):
            return src
    return "ddg"


def is_ai_answer(src: str | None = None) -> bool:
    """Does the source already return a synthesized answer (not just snippets)?"""
    return (src or provider()) in ("perplexity", "tavily", "openai", "gemini", "google")


# ── IS THE SEARCH LAYER ALIVE? (V2-176, 2026-08-20) ──────────────────────────────────────────────────────────
# When every backend in the chain fails, `search()` returns `results: []` with `source: "none"` — which is
# INDISTINGUISHABLE from «I searched fine and there is nothing». The only trace of the collapse was a
# `logger.warning`, so the brain composing the next turn could not tell the two apart and said the only thing it
# had: «sigo con ello».
#
# Measured on `cheapest-monitor`: twenty search events, no candidates, and ten turns of «te aviso en cuanto lo
# tenga» ending in «Hecho, te aviso al momento». The watchdog fired `stuck/nudge` while it happened. The search
# chain was down (quota exhausted plus a CAPTCHA) — so the outcome was never reachable, and the ONE thing that
# was reachable, saying so, was impossible: nothing carried the fact.
#
# Same remedy as the LLM side (`provider_chain.note_failure` + `health_state.record`): the layer records its own
# health, and the turn reads it. Classified into engine-native buckets — deliberately NOT by importing the test
# harness's needle list, which reads the same reality from the other end and must stay independent.
_FAILURE_MEMORY_S = 600.0
_last_failure: dict = {}

_FAIL_KINDS = (
    ("quota", ("limit exhausted", "quota", "rate limit", "429", "too many requests", "insufficient")),
    # The needles have to be the words the CHALLENGE PAGE actually uses, not the words we would use to
    # describe it. Measured 2026-08-27 against a live DuckDuckGo block: the page says «Unfortunately, bots use
    # DuckDuckGo too… Select all squares containing a duck» and the string "captcha" appears NOWHERE in it, so
    # a list built out of plausible names classified a hard block as a generic "error".
    ("captcha", ("captcha", "unusual traffic", "/sorry/", "are you a robot", "recaptcha", "access denied",
                 "made by a human", "squares containing", "bots use duckduckgo")),
    ("credential", ("api key", "unauthorized", "401", "403", "forbidden", "invalid key")),
    ("network", ("timeout", "timed out", "connection", "dns", "unreachable", "ssl")),
)


def _classify_failure(text: str) -> str:
    low = (text or "").lower()
    for kind, needles in _FAIL_KINDS:
        if any(n in low for n in needles):
            return kind
    return "error"


def note_failure(detail: str) -> None:
    """The whole chain came back with nothing → remember it, and light the operator's semaphore.

    «Estado visible, no silencioso»: a search layer that is down and shows green is indistinguishable from an
    agent that will not search, and the operator debugs the wrong thing.
    """
    global _last_failure
    kind = _classify_failure(detail)
    _last_failure = {"at": _time.time(), "kind": kind, "detail": (detail or "")[:200],
                     "n": int((_last_failure or {}).get("n") or 0) + 1}
    _hooks.chain_failed(kind, (detail or "")[:200] or "search chain down")


def note_success() -> None:
    """A backend answered → the layer is alive again and the fact stops being told."""
    global _last_failure
    _last_failure = {}


def recent_failure(now: float | None = None) -> dict:
    """The chain's last collapse if it is still recent, else {}. Read by the turn state, never by the searcher."""
    f = _last_failure or {}
    if not f:
        return {}
    now = _time.time() if now is None else now
    if (now - float(f.get("at") or 0)) > _FAILURE_MEMORY_S:
        return {}
    return dict(f)


#: How long an already-fetched answer remains valid. Deliberately SHORT — see `_recent_answer`.
_REPEAT_TTL_S = 120
#: Bounded: this lives in the engine process; it is not a data store.
_REPEAT_MAX = 64
_recent: dict[str, tuple[float, dict, int]] = {}


def _norm_q(q: str) -> str:
    return " ".join((q or "").lower().split())


def _recent_answer(q: str, now: float | None = None) -> tuple[dict, int] | None:
    """The answer we ALREADY fetched for this same query, if it is still fresh.

    Measured in `weekend-plan-barcelona__es` (2026-08-28): **56 web searches, 31 queries, 0 verified candidates**,
    repeating the same query without changing a single criterion. The judge: «that is not diligence, it is going
    around in circles». Each loop costs client seconds, provider quota, and a conversation turn in which zaelar says
    it is still searching.

    Repetition is NOT blocked; it is ANSWERED — and marked. Blocking would break a legitimate retry; returning the
    same thing instantly cuts the loop just as well and also records the fact (`repeated`) for whoever reads the
    round, turning «went around in circles» from an impression into data.

    The TTL is deliberately short (120 s), and that is the whole design: long enough to kill a tight loop —56 searches
    in nine minutes—, short enough for a human-paced «look again» to bring fresh information. A search cache that
    lasts longer than a person's patience serves stale data to someone who asked for the opposite.
    """
    now = _time.time() if now is None else now
    hit = _recent.get(_norm_q(q))
    if not hit:
        return None
    ts, res, n = hit
    if now - ts > _REPEAT_TTL_S:
        _recent.pop(_norm_q(q), None)
        return None
    return res, n


def _remember_answer(q: str, res: dict, now: float | None = None) -> None:
    now = _time.time() if now is None else now
    key = _norm_q(q)
    n = (_recent.get(key) or (0.0, {}, 0))[2]
    if len(_recent) >= _REPEAT_MAX and key not in _recent:
        _recent.pop(min(_recent, key=lambda k: _recent[k][0]), None)   # the oldest
    _recent[key] = (now, res, n + 1)


def search(query: str, k: int = _MAX_RESULTS, mode: str = "answer") -> dict:
    """Searches and returns `{query, answer, results:[{title,snippet,url}], source, ai}`.

    `mode="answer"` (default) wants a FACT: the synthesised providers go first. `mode="results"` wants PAGES to
    open (listing discovery, a local service): providers whose urls are real pages go first and the answer-only
    ones are skipped. Same cache, same failure memory, same metering.

    `answer` = already synthesized answer if the source is an AI-answer provider (Perplexity/Tavily); otherwise an
    empty string, composed by the brain from `results`. `ai` = True if `answer` is pre-synthesized (the brain only
    adapts it to voice/language). BLOCKING (network): ALWAYS call with `asyncio.to_thread`. Fail-open (degrades along
    the chain)."""
    q = (query or "").strip()
    if not q:
        return {"query": q, "answer": "", "results": [], "source": "none", "ai": False}
    # HAVE WE ALREADY ANSWERED THIS? Before spending network, quota, and client seconds again (see `_recent_answer`).
    _ya = _recent_answer(q if mode == "answer" else f"{mode}:{q}")
    if _ya is not None:
        _res, _veces = _ya
        _out = dict(_res)
        _out["repeated"] = {"n": _veces, "ttl_s": _REPEAT_TTL_S}
        _remember_answer(q if mode == "answer" else f"{mode}:{q}", _res)
        return _out
    _why: list[str] = []
    for src in (_order() if mode == "answer" else _order(mode)):
        try:
            r = _within(_RUNG_WALL_S, _BACKENDS[src], q, k)
            if r["results"] or r["answer"]:
                # respect the `ai` flag set by the backend (google marks ai=True if it returns AI Overview/featured);
                # by default, the rest are only the paid AI-answer providers.
                r["ai"] = bool(r.get("ai")) or src in ("perplexity", "tavily", "openai", "gemini")
                _meter_search(src)
                note_success()
                _answered(src)
                _remember_answer(q if mode == "answer" else f"{mode}:{q}", r)
                return r
            _why.append(f"{src}: sin resultados")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"websearch backend '{src}' falló, siguiente: {e}")
            _why.append(f"{src}: {_brief(e, 120)}")
            _set_aside_if_lasting(src, str(e))
    # THE CHAIN COLLAPSED. Recorded, not just logged — see `note_failure`. An empty result on its own cannot tell
    # the brain whether the world has nothing or our searching is broken, and those two deserve opposite replies.
    detail = " · ".join(_why)
    note_failure(detail)
    # THE REASON TRAVELS WITH THE RESULT. `note_failure` lights the operator's semaphore, but the observability
    # row for this search carried only `n: 0` — no word anywhere about why — so anything reading the stream
    # afterwards (the use-case harness's `search_health`, the operator auditing a round) could not tell a hard
    # block from an empty world, and graded the agent for not finding what nobody let us look for.
    return {"query": q, "answer": "", "results": [], "source": "none", "ai": False,
            "failure": {"kind": _classify_failure(detail), "detail": detail[:200]}}


# PAID ones, by backend name. `google` (our Chromium) and `ddg` are NOT included and therefore are not
# charged — being free is a property of the provider, declared ONCE in `search/providers` (`paid=True`), not a
# zero fee someone could misread. A paid search engine also needs a rate in
# `energy_meter._SEARCH_USD_PER_REQUEST`; the Energy coverage gate fails otherwise.
_PAID_BACKENDS = _paid_providers()


def _meter_search(src: str) -> None:
    """A ENERGY (2026-08-13). This family is metered PER REQUEST, not by tokens. Only what ANSWERED is metered: a
    backend that fails before answering is not metered. Gemini and Z.ai meter INSIDE their own module (`search/providers/*`), where
    the host string the Energy coverage gate greps for lives; they are listed in `_PAID_BACKENDS` so the gate
    that demands a rate for every paid backend still sees them."""
    if src not in _PAID_BACKENDS or src in ("openai", "gemini", "zai"):
        return
    from nucleo.energy import meter as _energy
    _energy.report_search_usage(provider=src)   # the counter does not raise: `@_never_raises` lives in the module


def _order(mode: str = "answer") -> list[str]:
    """Provider chain to try: the selected one first, then quality degradation down to the free option.
    `google` (free, browser) comes above `ddg` (last resort without a key or browser)."""
    chain = [provider(mode)]
    for fb in (_RESULTS_ORDER if mode == "results" else _ANSWER_ORDER):
        if fb not in chain and _usable(fb):
            chain.append(fb)
    if "ddg" not in chain:
        chain.append("ddg")               # the keyless rung is always appended
    return chain


# ── A RUNG HAS A WALL CLOCK (2026-10-23) ─────────────────────────────────────────────────────────────────────
# An httpx timeout bounds each PHASE (connect, every read), not the call: a server that keeps a trickle of bytes
# coming never trips it. Measured on a grounded Gemini call: 204 s for one rung, with an 18 s timeout set, while
# the turn waited for a fact. The bound belongs to the CHAIN, so every index — the ones declared today and the
# next one — gets it without remembering to: past `_RUNG_WALL_S` the rung counts as failed and the next one is
# asked. The abandoned call finishes on its own daemon thread; nothing waits for it.
_RUNG_WALL_S = float(os.getenv("WEBSEARCH_RUNG_WALL_S", str(_TIMEOUT + 10.0)))


def _within(wall_s: float, fn, *args):
    """`fn(*args)` bounded by `wall_s` seconds of wall clock. Raises `TimeoutError` past it; re-raises fn's error."""
    import threading
    box: dict = {}

    def run():
        try:
            box["ok"] = fn(*args)
        except BaseException as e:  # noqa: BLE001 — handed back to the caller's thread as is
            box["err"] = e

    t = threading.Thread(target=run, daemon=True, name="websearch-rung")
    t.start()
    t.join(wall_s)
    if t.is_alive():
        raise TimeoutError(f"rung over its wall clock ({wall_s:.0f} s)")
    if "err" in box:
        raise box["err"]
    return box["ok"]


# ── A LASTING REFUSAL SETS THE INDEX ASIDE (2026-10-23) ──────────────────────────────────────────────────────
# A quota refusal, a captcha or a refused key does not clear in the next second, yet every search asked the same
# index again first and paid its refusal before moving on (measured: Gemini on a free-tier key answered 429 from
# the 7th call of a minute on). Such an index is skipped for a window, then asked again — a quota that reset comes
# back on its own. How long:
#   1. the wait the PROVIDER names, when it names one (`retryDelay`, `Retry-After`, «try again in 20s»);
#   2. an account with no funds left does not refill by itself: `_NO_FUNDS_S`;
#   3. otherwise `_ASIDE_S`, doubled on each refusal in a row (an index still refusing after its window is
#      probably refusing for longer) up to `_ASIDE_MAX_S`; one answer clears the count.
# A network blip or an empty answer is not lasting and sets nothing aside. The keyless last resort (`ddg`) is always
# appended by `_order`, aside or not: an empty chain is worse than one more try. The memory is per process: a
# restart asks every index again, once.
_ASIDE_S = float(os.getenv("WEBSEARCH_ASIDE_S", "120"))
_ASIDE_MAX_S = float(os.getenv("WEBSEARCH_ASIDE_MAX_S", "3600"))
_NO_FUNDS_S = float(os.getenv("WEBSEARCH_NO_FUNDS_S", str(6 * 3600)))
_LASTING = tuple(kind for kind, _ in _FAIL_KINDS if kind != "network")   # a blip clears by itself
#: The wording providers use for an EMPTY WALLET (HTTP 402, billing pages) — not a rate limit that resets.
#: Not «billing»: Gemini's per-minute 429 says «check your plan and billing details».
_NO_FUNDS = ("http 402", "no api credits", "credits remaining", "out of funds", "insufficient balance",
             "insufficient_quota", "payment required")
_WAIT_RE = _re.compile(r'(?:retry[-_ ]?after|retrydelay|try again in)["\s:=]*"?(\d+(?:\.\d+)?)\s*(ms|s|m|h)?',
                       _re.I)
_aside: dict[str, float] = {}
_strikes: dict[str, int] = {}


def _named_wait(detail: str) -> float:
    """Seconds the provider said to wait, 0 when it did not say. Pure."""
    m = _WAIT_RE.search(detail or "")
    if not m:
        return 0.0
    n, unit = float(m.group(1)), (m.group(2) or "s").lower()
    return n / 1000 if unit == "ms" else n * {"s": 1, "m": 60, "h": 3600}[unit]


def _aside_window(src: str, detail: str) -> float:
    named = _named_wait(detail)
    if named > 0:
        return min(max(named, 30.0), _NO_FUNDS_S)
    if any(n in (detail or "").lower() for n in _NO_FUNDS):
        return _NO_FUNDS_S
    return min(_ASIDE_S * 2 ** (_strikes.get(src, 1) - 1), _ASIDE_MAX_S)


def _set_aside_if_lasting(src: str, detail: str, now: float | None = None) -> None:
    if _classify_failure(detail) in _LASTING or any(n in (detail or "").lower() for n in _NO_FUNDS):
        _strikes[src] = _strikes.get(src, 0) + 1
        _aside[src] = (_time.time() if now is None else now) + _aside_window(src, detail)


def _answered(src: str) -> None:
    _strikes.pop(src, None)


def set_aside(now: float | None = None) -> dict[str, float]:
    """Indexes currently set aside → seconds left. For the health line and whoever audits a round."""
    now = _time.time() if now is None else now
    return {s: round(t - now, 1) for s, t in _aside.items() if t > now}


def _usable(src: str) -> bool:
    if _aside.get(src, 0.0) > _time.time():
        return False
    if src == "google":
        return _google_on()
    if src == "ddg":
        return True
    try:
        return _keys.present(src)
    except KeyError:
        return False


# ── Perplexity Sonar (synthesized AI answer + citations) ──────────────────────────────────────────────────
def _perplexity(q: str, k: int) -> dict:
    import httpx
    if not perplexity_key():
        return {"query": q, "answer": "", "results": [], "source": "perplexity"}
    model = os.getenv("PERPLEXITY_MODEL", "sonar")
    headers = {"Authorization": f"Bearer {perplexity_key()}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [
        {"role": "system", "content": "Be precise and concise. Answer with the latest facts."},
        {"role": "user", "content": q}]}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    answer = _clean(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    cites = data.get("citations") or []
    results = [{"title": "", "snippet": "", "url": u} for u in cites[:k] if isinstance(u, str)]
    return {"query": q, "answer": answer, "results": results, "source": "perplexity"}


# ── Tavily (search API for agents: answer + clean sources) ─────────────────────────────────────────────────
def _tavily(q: str, k: int) -> dict:
    import httpx
    if not tavily_key():
        return {"query": q, "answer": "", "results": [], "source": "tavily"}
    payload = {"api_key": tavily_key(), "query": q, "search_depth": "advanced",
               "include_answer": True, "max_results": max(1, min(k, 10))}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
    results = [{"title": _clean(r.get("title") or ""), "snippet": _clean(r.get("content") or ""),
                "url": (r.get("url") or "").strip()} for r in (data.get("results") or [])[:k]]
    return {"query": q, "answer": _clean(data.get("answer") or ""), "results": results, "source": "tavily"}


# ── Brave Search API (clean snippets, optionally with key) ────────────────────────────────────────────────
def _brave(q: str, k: int) -> dict:
    import httpx
    if not brave_key():
        return {"query": q, "answer": "", "results": [], "source": "brave"}
    headers = {"X-Subscription-Token": brave_key(), "Accept": "application/json", "User-Agent": _UA}
    params = {"q": q, "count": max(1, min(k, 10))}
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        resp = c.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = [{"title": _clean(it.get("title") or ""), "snippet": _clean(it.get("description") or ""),
                "url": (it.get("url") or "").strip()} for it in ((data.get("web") or {}).get("results") or [])[:k]]
    ib = data.get("infobox") or {}
    answer = _clean(ib.get("long_desc") or ib.get("description") or "") if isinstance(ib, dict) else ""
    return {"query": q, "answer": answer, "results": results, "source": "brave"}


# ── Google via our own Chromium (FREE, AI Overview + snippets; V2-024) ─────────────────────────────────────
def _google(q: str, k: int) -> dict:
    """Google search in the persistent headless browser (`search/browser`). BLOCKING from the `to_thread`
    thread: the `search_sync` bridge schedules the coroutine on the server loop. Raises if the browser is not ready
    or Google blocks → the chain degrades to DDG (fail-open)."""
    if not _google_on():
        return {"query": q, "answer": "", "results": [], "source": "google"}
    from search import browser as browser_search
    return browser_search.search_sync(q, k)


# ── DuckDuckGo HTML (free, no key, always available) ───────────────────────────────────────────────────────
_SNIPPET_RE = _re.compile(r'result__snippet[^>]*>(.*?)</a>', _re.S)
_LINK_RE = _re.compile(r'result__a[^>]*href="(.*?)"[^>]*>(.*?)</a>', _re.S)



def _accept_language() -> str:
    """The header that tells a site which country it is serving. It was pinned to `es-ES` for everybody, and a
    header outranks the words of the query: measured 2026-08-27, a US search for hotels under $150 came back
    priced in euros. Follows the engine's own language, with English when it cannot be read (the product
    default — an unreadable language never silently becomes Spanish)."""
    try:
        from i18n import langs as _langs
        code = (_langs.current_code() or "en").lower()
    except Exception:  # noqa: BLE001 — a web search must never die because the language is unreadable
        code = "en"
    if code == "es":
        return "es-ES,es;q=0.9,en;q=0.8"
    return f"{code}-US,{code};q=0.9" if code == "en" else f"{code},{code};q=0.9,en;q=0.8"

_CHALLENGE = ("made by a human", "squares containing", "bots use duckduckgo", "captcha",
              "unusual traffic", "are you a robot")


def _challenge_reason(body: str) -> str:
    """Non-empty when the page we were served is a bot CHALLENGE rather than a result list.

    It exists because the block does not arrive as an error. Measured 2026-08-27: a blocked DuckDuckGo answers
    **HTTP 202** with a challenge page, and 202 is a success status — `raise_for_status()` waves it through,
    the link regex finds nothing, and the caller gets `results: []`. "We were blocked" and "the world has
    nothing" then look identical, which are opposite facts deserving opposite replies (the same reason
    `note_failure` exists at all). `browser_search._looks_blocked` already does this for Google; DDG, the last
    rung of the chain and the one that runs when everything else is missing, had nothing.
    """
    low = (body or "")[:4000].lower()
    hit = next((n for n in _CHALLENGE if n in low), "")
    return f"captcha: DuckDuckGo served an anti-bot challenge («{hit}»)" if hit else ""


def _ddg(q: str, k: int) -> dict:
    import httpx
    answer = _ddg_instant(q)
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        resp = c.post("https://html.duckduckgo.com/html/", data={"q": q},
                      headers={"User-Agent": _UA, "Accept-Language": _accept_language()})
        resp.raise_for_status()      # NOT enough on its own: a block comes back as 202, a success status
        body = resp.text
    blocked = _challenge_reason(body)
    if blocked:
        raise RuntimeError(blocked)      # so the chain's reason string SAYS it instead of "sin resultados"
    links = _LINK_RE.findall(body)
    snippets = _SNIPPET_RE.findall(body)
    results = _assemble_ddg_results(links, snippets, k)
    return {"query": q, "answer": answer, "results": results, "source": "ddg"}


def _is_ad(url: str) -> bool:
    """A search-engine AD is not a search result (V2-469): measured in `cheapest-monitor__us`, DDG's
    `y.js?ad_domain=…&ad_type=txad` redirects landed in the sheet as the first two «candidates», with
    SPANISH titles on the US engine — ads follow the machine's IP, not the engine's locale. Recognized by
    the redirect's SHAPE (ad host path / ad params), never by words in a page's own path."""
    u = str(url or "")
    try:
        p = urlparse(u)
        if "duckduckgo.com" in (p.netloc or "") and p.path.startswith("/y.js"):
            return True
        q = p.query or ""
        return "ad_provider=" in q or "ad_type=" in q
    except Exception:  # noqa: BLE001
        return False


def _assemble_ddg_results(links: list, snippets: list, k: int) -> list:
    """Pair links with snippets and keep the first k ORGANIC rows — ads are skipped at the source so no
    consumer downstream (brain note, worker lead, results sheet) ever sees them."""
    out = []
    for i, sn in enumerate(snippets):
        href, title = (links[i] if i < len(links) else ("", ""))
        url = _ddg_href(href)
        if _is_ad(url):
            continue
        out.append({"title": _clean(title), "snippet": _clean(sn), "url": url})
        if len(out) >= k:
            break
    return out


def _ddg_instant(q: str) -> str:
    import httpx
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
            resp = c.get("https://api.duckduckgo.com/",
                         params={"q": q, "format": "json", "no_html": "1", "skip_disambig": "1"},
                         headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.json()
        return _clean(data.get("AbstractText") or data.get("Answer") or "")
    except Exception:
        return ""


def _ddg_href(href: str) -> str:
    href = _html.unescape(href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        u = urlparse(href)
        if "duckduckgo.com" in (u.netloc or "") and u.path.startswith("/l/"):
            uddg = parse_qs(u.query).get("uddg", [""])[0]
            if uddg:
                return unquote(uddg)
    except Exception:
        pass
    return href


def _openai(q: str, k: int) -> dict:
    from .providers import openai as _p
    return _p.search(q, k)


def _gemini(q: str, k: int) -> dict:
    from .providers import gemini as _p
    return _p.search(q, k)


def _zai(q: str, k: int) -> dict:
    from .providers import zai as _p
    return _p.search(q, k)


_BACKENDS = {"perplexity": _perplexity, "tavily": _tavily, "openai": _openai, "gemini": _gemini, "zai": _zai, "brave": _brave,
             "google": _google, "ddg": _ddg}


def _clean(s: str) -> str:
    s = _re.sub(r"<[^>]+>", "", s or "")
    s = _html.unescape(s)
    return _re.sub(r"\s+", " ", s).strip()


def format_results(res: dict, limit: int = _MAX_RESULTS) -> str:
    """Packages the search as context so the brain can compose the answer (or adapt it to voice if already
    synthesized). If `answer` comes from an AI-answer provider, it is highlighted as the main answer."""
    parts: list[str] = []
    if res.get("answer"):
        label = "RESPUESTA (ya sintetizada por el buscador IA)" if res.get("ai") else "Respuesta directa del buscador"
        parts.append(f"{label}: {res['answer'][:1200]}")
    for i, r in enumerate(res.get("results", [])[:limit], 1):
        line = f"[{i}] {r.get('title', '')} — {r.get('snippet', '')}".strip(" —")
        if line and line != f"[{i}]":
            parts.append(line[:400])
    return "\n".join(parts)
