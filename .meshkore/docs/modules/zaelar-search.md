---
title: The search service (search/)
category: modules
updated: 2026-10-10
owner: ricart
status: current
---

# The search service — one door in, one result shape out

`search/` (engine). Search is a service with one entry point, so that a single place answers «this request →
this module». This document is its MAP: entry points, providers, caches, timeouts, fail-open rules, and what
each one returns. Mechanism only.

## The one door

```python
from search import find
res = find("fontanero urgente en Madrid, el mejor valorado")   # blocking; callers on a loop use asyncio.to_thread
res.route        # inline_fact · listing · local_service · images · browser · brain_worker
res.provider     # gemini · zai · ddg · google · listing ladder · foursquare · …
res.answer       # a synthesised answer when the provider gave one
res.candidates   # [Candidate]: one thing each, with a datum of its own (price · rating · phone · availability)
res.pages        # [Page]: rankings / articles / policy pages — kept in Sources with the reason, never counted
res.sources      # [Source]: every door tried, with status
res.criteria     # {hard, fields, n_final, min_candidates} — what the request itself asked for
res.unshown      # the hard criteria NO candidate carries a datum for → said missing, never implied met
res.needs        # "" · browser · brain_worker — what the service cannot run itself; the caller commissions it
res.failure      # {kind, detail} when the chain collapsed (captcha · quota · credential · network · error)
```

`find()` never raises. The HTTP face serves the same thing: `POST /api/search/find`, `POST /api/search/route`
(no network), `GET /api/search/health` (one minimal real call per provider, cached 120 s). Guarded like every
`/api/*` route (loopback or token).

## The pieces

| Module | Role | Returns |
|---|---|---|
| `route.py` | WHICH module serves a request. Reads the brief's `search_module` verdict, the model's tool proposal, the escalate verdict and the errand surface — in that precedence (CRIT-K2). No verb tables. | `Route(module, why, confidence, breadth, fields)` |
| `criteria.py` | What the request SAYS about how many («a couple» = 3, «tres» = 3, «un piso» ≠ 1) and which data fields (price · rating · availability). ES + EN numerals and field words. | `{n_final, min_candidates, said, fields, hard}` |
| `candidacy.py` | A row is a CANDIDATE (a datum of its own) or the PAGE that lists candidates (title counts/ranks a category; url is an article/policy page). A phone shared by rows is the site's switchboard, not a datum. | `split(rows) → (candidates, pages)`, `unshown_criteria(rows, criteria)` |
| `result.py` | The one shape: `Candidate`, `Page`, `Source`, `SearchResult`; the sheet rows (`to_row()`, closed schema, phone/rating/availability/origin as facts, both languages). | — |
| `web.py` | The fact/lead CHAIN (was `nucleo/websearch.py`). `search(query, k, mode)`: `answer` → Perplexity → Tavily → **OpenAI** → **Gemini** → **Z.ai** → Brave → Google (Chromium) → DDG; `results` → Z.ai → Brave → OpenAI → Tavily → Google → DDG. 120 s repeat cache per mode; failure memory 600 s; `WEBSEARCH_PROVIDER` override. | `{query, answer, results[{title,snippet,url}], source, ai, failure?, repeated?}` |
| `listing.py` + `extract.py` | The listing LADDER (was `nucleo/listing_search.py` + `listing_extract.py`): SERP (Bright Data, keyed) or `web.search(mode="results")` → HTTP fetch (unlocker when keyed; per-domain politeness, 403/429 strikes) → JSON-LD / OpenGraph extraction → price filter → dedup. 30 min cache; `deadline_s` cuts work, never honesty. | `{items, sources, exhausted, needs_browser, reason}` |
| `browser.py` + `images.py` | The warm Chromium (was `nucleo/browser_search.py`): Google search and the image chain Google → Yandex → Bing with a 7-day answer cache; `search_sync` / `images_sync` bridges for threads. Pure parsers in `images.py`. | web contract · `{items, source, blocked, degraded_from?}` |
| `providers/` | Every external index declared ONCE: `Provider(name, kind, keys, paid, host)`. `keys.py` resolves by NAME. `openai.py`, `zai.py`, `gemini.py`, `foursquare.py` are one POST each with a pure `parse()` tested on a recorded payload. | — |
| `health.py` | One minimal real call per provider → `live · missing · off · exhausted · credential · blocked · network · down · engine`. `python -m search.health [--json] [--engine URL]`. | rows + `summary()` (`can_answer`, `can_discover`, `can_place`) |
| `hooks.py` | The two seams the host wires at boot: `on_chain_failure` (status light) and `emit` (timeline). Unset = no-ops. | — |
| `api.py` | The HTTP face. | — |

The old import paths (`nucleo.websearch`, `nucleo.listing_search`, `nucleo.listing_extract`,
`nucleo.browser_search`, `nucleo.image_search`) are aliases bound to the SAME module objects, so every caller and
every test that patches through them keeps working. New code imports `search.*`.

## Providers and keys (names only)

| Provider | Kind | Key (env) | Paid | Notes |
|---|---|---|---|---|
| perplexity | answer | `PERPLEXITY_API_KEY` / `PPLX_API_KEY` | yes | Sonar; synthesised answer + citations |
| tavily | answer | `TAVILY_API_KEY` | yes | answer + clean sources |
| openai | answer | `OPENAI_API_KEY` | yes | Responses API `web_search_preview`: answer + cited PAGES (title + real url, no redirect); `OPENAI_SEARCH_MODEL` (default `gpt-4.1-mini`) |
| gemini | answer | `GEMINI_API_KEY` | yes | Google Search grounding; cited domains, redirect urls; `GEMINI_SEARCH_MODEL` (default `gemini-2.5-flash`) |
| zai | results | `Z_AI_API_KEY` | yes | Z.ai Web Search API, pay per call, a DIFFERENT wallet from the coding plan's MCP quota; `ZAI_SEARCH_ENGINE` (default `search-prime`) |
| brave | results | `BRAVE_SEARCH_KEY` / `BRAVE_API_KEY` | yes | ranked pages |
| google | results | — (`BROWSER_SEARCH=0` turns it off) | no | our Chromium; captcha-prone; needs the engine loop |
| ddg | results | — | no | last resort; a block arrives as HTTP 202 with a challenge page |
| foursquare | places | `FOURSQUARE_SERVICE_KEY` | yes | phone, rating, open-now for a local service; parser written against the API docs |
| brightdata_serp / brightdata_unlocker | serp / unlocker | `BRIGHTDATA_API_TOKEN` (+ `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE`) | yes | listing discovery and fetch through bot walls |
| images | images | — | no | Google → Yandex → Bing in our Chromium |

Every paid provider has a rate in `search/providers/__init__.py::USD_PER_REQUEST` (beside its declaration; `nucleo/energy/meter`
reads it and adds the catch-all row; the metering coverage gate fails otherwise) and meters only what ANSWERED. Timeouts: `WEBSEARCH_TIMEOUT` (12 s; Gemini +6), `LISTING_SEARCH_TIMEOUT`,
`BROWSER_SEARCH_TIMEOUT`.

## How the turn uses it

- **The two fact doors** (`web_search` on the voice channel, `post_stream_lanes`; and on the probe, `probe_after`) call
  `find(query, route="inline_fact", proposal="web_search")` and read `raw` (the chain's dict) for the composing pass.
- **The worker** searches with `python -m nucleo.cli.bridge act use_tool "<query>"` — a quoted sentence, no JSON,
  no file (the form the worker's confinement guard accepts). `worker_api` runs `find()` and returns the
  chain dict plus `route`, `candidates` (sheet rows), `pages` and `unshown`; the rows reach the errand's sheet as before.
- **The status panel** (`/api/status`) carries one line, «Búsqueda · proveedores», from the LAST probe (primed once
  45 s after boot, refreshed by `/api/search/health`), never probing on a poll.

- The turn brief asks Jev the routing question (`search_module`, `route.question()`) in the same trip as its
  other questions. `nucleo/flash/search_routing.py` reads the verdicts and emits the route the service would take
  as `🧭 ruta de búsqueda (sombra)` on both channels next to every `web_search` — **shadow mode**: the route is
  recorded beside the current path, so it can be validated against real sessions before it takes over.
- The sheet's `present` / `append` (`widgets/results/actions.py`) apply `candidacy.split` to every batch and return
  `not_candidates`, `criteria_unshown` and a `note_for_worker`; the prompt digest says the criterion no row shows.
- A network agent's rows (`nucleo/cli/mesh._to_the_sheet`) travel as `Candidate(origin="mesh")`, keep rating, phone
  and location, and are capped at 8 per batch.
- The research brief respects the size the operator said (`research.parse(raw, request)` → `criteria.breadth`).
- The listing ladder's free discovery asks `web.search(mode="results")`, so Z.ai (keyed) discovers pages instead of a
  captcha'd Google.
- The use-case harness refuses to grade a batch when `/api/search/health` says no provider can answer (exit 4, INFRA).

## Boundaries and extension points

- `search_listings` (the listing fast pass, `flash/listing_turn.run`) calls `listing.search` directly — it already IS
  the service's ladder and owns the sheet handoff; `images` (`image_turn`) calls `browser.images` directly. Both carry
  the service's shape through the sheet doors.
- `find()` for a `local_service` uses a places provider when one is keyed; otherwise it falls back to the lead
  chain — names and links — and `unshown` says which requested data those rows cannot show.
- Candidacy is structural: a row with a datum of its own and a link is a candidate. Category relevance is left to
  the reasoning layer; network-agent rows carry their `mesh` origin and are capped per batch.
- New providers plug in by declaring a `Provider` in `providers/` with a pure `parse()` and a health probe.

## The extractor's furniture rules (from recorded pages)

`extract.extract_items` returns ZERO, with the reason in `listing.search`'s `sources`, for: a category page priced by an
`AggregateOffer` (coches.net), a list page whose only JSON-LD node is its own unpriced description (fotocasa), a search
page whose list items are bare urls (autoscout24, motos.net). A single priced node whose url is the page is a true
detail page and is kept. Recorded pages live under `tests/search/fixtures/pages/`.

Tests: `tests/search/` (domain 12 of `tests/run_testmap.py`), fixtures recorded under
`tests/search/fixtures/` (real OpenAI, Z.ai and Gemini payloads; marketplace pages; recorded results sheets).
Live canary: `ZAELAR_TEST_LIVE_SEARCH=1 pytest tests/search/live` — a few cents, loose
assertions, never part of the deterministic sweep.
