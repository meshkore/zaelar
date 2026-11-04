# `scrape/` — reading a page (V2-846)

`search/` finds pages; `scrape/` gets to a page and reads it. One door, the ladders inside — the caller never chooses.

```python
from scrape import read
res = read(url, want="listings" | "page", country="")   # → ScrapeResult
res.how, res.records, res.extractor, res.tried, res.failure
```

HTTP: `POST /api/scrape/read {url, want?, country?}` → the records and how they came (never the HTML).

## Fetch ladder (`fetch.py`)

| rung | what | moves up when |
|---|---|---|
| `http` | a plain GET from this machine, per-domain politeness (interval, rest after repeated 403/429, `Retry-After`) | a wall (`walls.py`: blocking status, challenge page, the site's own error page) or a page with no records |
| `unlocker` | Bright Data's Web Unlocker (`brightdata.py`, one client for both zones, through mediated egress, metered on success) | the provider's own refusal (`x-brd-error`, e.g. KYC for robots-restricted sites) is raised, never taken for the page |

The browser rungs (the Machine's Chromium, and a residential one over CDP relayed by the gateway) join in F3/F4.
Each wall is noted in the engine's one per-source record (CRIT-E17) through `hooks.note_source`.

## Extract ladder

1. **declared** — JSON-LD / OpenGraph (`extract.py`, with the row utilities every rung shares: price parsing, dedup,
   price filter, canonical URLs).
2. **state** — `state.py` decodes every JSON the scripts carry (`<script type=…json>`, `__NEXT_DATA__`,
   `= JSON.parse("…")`, `window.X = {…}`) and picks the listings array by the SHAPE of the values: items that carry a
   link and words, rich objects (a navigation list of two-field links never wins). Fields are chosen by value: the
   shallowest path, then the one that differs most across items, a link on the page's own site first. What values
   cannot say (a bare-number price, the figures that compare items) comes from a field map the model writes ONCE per
   site and per listing path (`mapping.py`, `hooks.map_fields`), kept as data in `memory/_data/scrape/mappings.json`.
   No generated code is ever run.

3. **markup** — `markup.py` over `dom.py` (a small DOM on the standard library's `html.parser`, with the one selector
   syntax `scrape/` keeps as data: `tag.class` steps): the listings are the children of ONE container that each carry a
   same-site link and a price; inside a card the fields are read by shape — the link whose text names the item, the
   amount its currency touches (even split across elements), the picture, short facts with figures.
4. **model** — last, and paid: when no free rung read the page, the fast model reads its text (links written after
   their words) ONCE per read, returning items as JSON (`hooks.read_with_model`).

The free rungs (1-3) are all asked and the one with MORE valid records wins (declared on a tie).

**One validator** (`validate.py`) for every rung: a title with words, a link on the page's own site (not the page
itself, not a picture host), a positive price when there is one, distinct links (a category page taken for each ad's
link fails), dedup. A rung whose records mostly fail does not count.

## Boundaries

- Never imports the turn, the workers, the dispatcher, `memory/`, `widgets/`, `voice/` or `server/`
  (`tests/scrape/unit/test_scrape_owes_the_engine_nothing.py`). Seams: `hooks.model`, `hooks.note`, wired in
  `server/boot/surfaces.py`.
- Blocking; callers on an event loop use `asyncio.to_thread`. Never raises.

Measured 2026-11-04 on real pages: AutoScout24 (`__NEXT_DATA__`), coches.net and milanuncios (escaped
`JSON.parse` state) went from 0 ads to every ad with price, link and comparing figures. Tests: `tests/scrape/`
(nodes 12.845-12.847). Plan and phases: `.meshkore/roadmap/initiatives/V2-846-*`.
