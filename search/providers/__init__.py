"""search/providers — every external index the search service can ask, declared ONCE (V2-782 F2).

A provider is a row here plus one module with a `search(query, k)` (or `places(...)`) function. The row carries
what the health probe, the chain order, the Energy gate and the operator's panel all need to know about it:
which env var holds its key (NAMES only, never values), whether it is paid, what it returns, and the host it
calls (the Energy coverage test greps for that host and demands a meter next to it).

Kinds, because callers want different things:
  · `answer`  — returns a synthesised answer with citations (Perplexity, Tavily, Gemini grounding). Best for a
    FACT the turn speaks; useless for discovering listing pages (its urls are redirects or domains).
  · `results` — returns ranked pages with title/snippet/url (Z.ai, Brave, Google via Chromium, DuckDuckGo).
    What listing discovery and local-service hunts need.
  · `places`  — a directory of businesses with phone/rating/hours (Foursquare). The only kind that captures the
    criterion a local-service request asks for.
  · `serp` / `unlocker` — Bright Data's two zones (parsed Google JSON; bot walls become 200s).
  · `browser` / `images` — our own warm Chromium (free, captcha-prone).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str
    keys: tuple[str, ...] = ()        # env var NAMES; empty = no key needed
    paid: bool = False
    host: str = ""
    note: str = ""
    verified_live: str = ""           # the day a real call from this repo was seen answering
    env_switch: tuple[str, str] = field(default=("", ""))   # (env var, value that disables it)


PROVIDERS: dict[str, Provider] = {
    "perplexity": Provider("perplexity", "answer", ("PERPLEXITY_API_KEY", "PPLX_API_KEY"), True, "api.perplexity.ai"),
    "tavily": Provider("tavily", "answer", ("TAVILY_API_KEY",), True, "api.tavily.com"),
    "openai": Provider("openai", "answer", ("OPENAI_API_KEY",), True, "api.openai.com",
                       "OpenAI Responses web search: answer + cited PAGES (real deep links)", verified_live="2026-10-10"),
    "gemini": Provider("gemini", "answer", ("GEMINI_API_KEY",), True, "generativelanguage.googleapis.com",
                       "Gemini with Google Search grounding: Google's index, answer + cited domains",
                       verified_live="2026-10-10"),
    "zai": Provider("zai", "results", ("Z_AI_API_KEY",), True, "api.z.ai",
                    "Z.ai Web Search API (pay per call; a different wallet from the coding plan's MCP quota)",
                    verified_live="2026-10-10"),
    "brave": Provider("brave", "results", ("BRAVE_SEARCH_KEY", "BRAVE_API_KEY"), True, "api.search.brave.com"),
    "google": Provider("google", "results", (), False, "www.google.com", "our own warm Chromium; captcha-prone",
                       env_switch=("BROWSER_SEARCH", "0")),
    "ddg": Provider("ddg", "results", (), False, "html.duckduckgo.com", "last resort; answers a bot challenge as HTTP 202"),
    "foursquare": Provider("foursquare", "places", ("FOURSQUARE_SERVICE_KEY",), True, "places-api.foursquare.com",
                           "Foursquare Places: name, phone, rating, open-now for a local service"),
    "brightdata_serp": Provider("brightdata_serp", "serp", ("BRIGHTDATA_API_TOKEN",), True, "api.brightdata.com",
                                "parsed Google JSON, geo-targeted; listing discovery"),
    "brightdata_unlocker": Provider("brightdata_unlocker", "unlocker", ("BRIGHTDATA_API_TOKEN",), True,
                                    "api.brightdata.com", "bot walls become 200s; listing fetch"),
    "images": Provider("images", "images", (), False, "www.google.com", "Google → Yandex → Bing, in our Chromium",
                       env_switch=("BROWSER_SEARCH", "0")),
}


def of_kind(kind: str) -> list[str]:
    return [p.name for p in PROVIDERS.values() if p.kind == kind]


def paid() -> frozenset[str]:
    return frozenset(p.name for p in PROVIDERS.values() if p.paid)
