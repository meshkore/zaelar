"""search/providers — every external index the search service can ask, declared ONCE (V2-782 F2).

A provider is a row here plus one module with a `search(query, k)` (or `places(...)`) function. The row carries
what the health probe, the chain order, the Energy gate and the operator's panel all need to know about it:
which env var holds its key (NAMES only, never values), whether it is paid, what it returns, and the host it
calls (the Energy coverage test greps for that host and demands a meter next to it).

Kinds, because callers want different things:
  · `answer`  — returns a synthesised answer with citations (Perplexity, Gemini grounding). Best for a
    FACT the turn speaks; useless for discovering listing pages (its urls are redirects or domains).
  · `results` — returns ranked pages with title/snippet/url (Tavily, Z.ai, Brave, Google via Chromium, DuckDuckGo).
    What listing discovery and local-service hunts need.
  · `places`  — a directory of businesses with phone/rating/hours (Foursquare). The only kind that captures the
    criterion a local-service request asks for.
  · `serp` / `unlocker` — Bright Data's two zones (parsed Google JSON; bot walls become 200s).
  · `browser` / `images` — our own warm Chromium (free, captcha-prone).
  · `video`   — YouTube videos (`search/video.py`): the results page, then the same page in the Chromium.
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
    "tavily": Provider("tavily", "results", ("TAVILY_API_KEY",), True, "api.tavily.com",
                       "Tavily basic search: ranked pages + a short answer; 1,000 free credits a month",
                       verified_live="2026-11-03"),
    "openai": Provider("openai", "answer", ("OPENAI_API_KEY",), True, "api.openai.com",
                       "OpenAI Responses web search: answer + cited PAGES (real deep links)", verified_live="2026-10-10"),
    "gemini": Provider("gemini", "answer", ("GEMINI_SEARCH_API_KEY", "GEMINI_API_KEY"), True, "generativelanguage.googleapis.com",
                       "Gemini with Google Search grounding: Google's index, answer + cited domains",
                       verified_live="2026-10-10"),
    "zai": Provider("zai", "results", ("ZAI_SEARCH_API_KEY", "Z_AI_API_KEY"), True, "api.z.ai",
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
    # V2-833 F1 — a video (or a track to play) is a search: `search/video.py`, page first, then the same page in our
    # Chromium. The music player, the video card and the channel reader all ask here.
    "youtube": Provider("youtube", "video", (), False, "www.youtube.com", "the results page over HTTP; free, fast"),
    "youtube_browser": Provider("youtube_browser", "video", (), False, "www.youtube.com",
                                "the results page in our warm Chromium (a real browser's fingerprint)",
                                env_switch=("BROWSER_SEARCH", "0")),
}


#: USD per paid request, an upper-bound estimate used for metering — re-verify against each provider's pricing. Read
#: by `nucleo.energy.meter._SEARCH_USD_PER_REQUEST` (which adds the catch-all row), so a provider declared above
#: without a row here is metered at the catch-all, loudly (`test_energy_coverage`).
USD_PER_REQUEST: dict[str, float] = {
    # Per call, re-read 2026-11-03 (the gateway's `families.js` carries the same numbers). Perplexity reports its own
    # cost per call: the `fast-search` preset $0.0015, `perplexity/sonar` + search tool $0.0042.
    "perplexity": 0.002,
    # Basic depth = 1 credit. The first 1,000 credits a month are free on the provider's side; the meter charges
    # the beyond-tier $0.008 every time, because a per-process counter cannot know the account's monthly total.
    "tavily": 0.008,
    "brave": 0.005,            # $5 per 1,000; the provider's $5 monthly credit is not visible per process either
    # Bright Data (V2-556): SERP API and Web Unlocker. Only SUCCESSFUL responses are metered
    # (`listing._bd_request` meters after the 200).
    "brightdata_serp": 0.0015,
    "brightdata_unlocker": 0.003,
    # Gemini: grounding ~$0.014 a prompt beyond the free monthly quota, plus its few hundred tokens. OpenAI: the
    # `web_search` tool call and its tokens, ~$0.01-0.025. Z.ai: its per-call web search wallet, ~$0.01.
    "gemini": 0.016,
    "openai": 0.025,
    "zai": 0.01,
    "foursquare": 0.005,
}


def paid() -> frozenset[str]:
    return frozenset(p.name for p in PROVIDERS.values() if p.paid)
