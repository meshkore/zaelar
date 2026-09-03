# Fotos — Google Photos Picker connector + virtualized gallery widget (V2-564)

## Anatomy

```
connectors/photos/
├─ providers.py     single-tier registry (Picker's only scope, non-browsable by nature)
├─ oauth.py         PKCE flow, same shape as connectors/files/oauth.py
├─ google_photos.py Picker API v1 HTTP client
├─ store.py         the durable LOCAL index — what makes browsing possible at all
├─ service.py       provider-agnostic facade + the past-oriented date-range parser
└─ server_api.py    /api/photos/* — account OAuth, poll, thumb proxy

widgets/fotos/
├─ manifest.json    actions: refresh · connect · more · search · clear_search · label_batch · disconnect
├─ data.py          cache-only view_data, network only in apply_action/tick
├─ widget.js         a virtualized grid — pure layout, windowed DOM mounting
└─ notes.md
```

## Why this isn't a normal "browse the cloud" connector

Every other cloud connector in this repo (`connectors/files/`) can re-list its source on demand — Drive
and OneDrive answer live queries. Google Photos cannot: since March 2025, no third-party app can read a
user's *existing* library at all (`photoslibrary.readonly` → 403 for everyone). The only surface left is
the **Picker API** — the user opens Google's own picker UI, hand-selects items/albums for ONE session, and
the app receives exactly those items, once.

That single fact shapes the whole connector:

- **`store.py` is the source of truth for browsing/searching, not Google.** Once a session's items are
  imported, they live in a local JSON index (`widgets/store.data_dir("fotos")`) forever — there is no way
  to re-derive them from Google later. `service.list_page()`/`service.search()` never touch the network.
- **A thumbnail is downloaded at import time**, while the session's signed `baseUrl` is still valid
  (Google states it lives roughly an hour). The widget's `<img>` tags point at our own
  `GET /api/photos/thumb/{id}`, which serves that cached JPEG — never Google's ephemeral URL.
- **A trip label is OUR OWN concept.** The Picker doesn't hand back an album name for a mixed selection, so
  the operator (voice or UI) attaches a label to the most-recently-imported batch. Search matches this label
  plus `taken_at`, never photo content.

## The date-range parser

`connectors/photos/service.py::_parse_date_hint` is deliberately a SEPARATE, small parser from
`nucleo/scheduler.py::parse_when` — that one is strictly future-facing (reminders: "tomorrow", "next
Thursday") and returns a single point in time. This one is past-oriented (photos already taken) and returns
a `(date_from, date_to)` range: "last year", "this year", "N years ago", a bare month (resolving to its most
recent past occurrence unless a year is given), or a bare 4-digit year. Anything else is treated as a pure
label search.

The one subtlety worth knowing before touching it: the phrase is matched against an accent-stripped copy of
the text (`_strip`, NFKD-decompose + drop combining marks — "año" → "ano"), but the matched **spans** are
used to blank out characters in the ORIGINAL string, never a string-substitution of the accent-free match.
Accent-folding a single Spanish letter is always 1-codepoint-in → 1-codepoint-out, so index alignment holds
between the stripped copy and the original.

## The virtualized grid

`widgets/fotos/widget.js` computes a pure layout (`buildRows`) — a list of rows, each either a year-header
or a row of item tiles — from the already-sorted item list and the current column count. Only rows within
one viewport-height of buffer above/below the visible scroll range get DOM nodes; scrolling recycles nodes
rather than accumulating them. This is the direct answer to "if I scroll through a thousand photos, that
shouldn't eat memory" — verified in `tests/browser/e2e/widgets/test_fotos_render.py` by rendering a 300-item
fixture and asserting the mounted `.fts-tile` count stays under 100, both before and after scrolling to the
bottom.

## Frontiers

- Voice transports intent only — `connect` returns a `url` to open, never a credential; the app's
  client_id/secret is registered once in ⚙ → Conectores (V2-520).
- `widget.js` never calls `fetch`/opens a socket — the picker session and paging go through declared
  actions; the only network-adjacent thing it does is set `<img src>` to our own thumb-proxy route, exactly
  like `widgets/imagenes/`.
- Apple Photos and Amazon Photos are catalog-only (`connectors/catalog/apple-photos.json`,
  `amazon-photos.json`, both `state: "not-possible"`) — no connector code exists for either, and none should
  be written until Apple or Amazon ship a real public API.
