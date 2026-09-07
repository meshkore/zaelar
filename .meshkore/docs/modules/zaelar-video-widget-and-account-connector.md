# The video widget and the video-account connector

**Pieces**: `widgets/youtube/` (the player card) + `connectors/video/` (the account family, V2-597).
Mechanism only — this repo is public.

## The widget (`widgets/youtube/`)

A REAL embedded YouTube player (`<iframe>`, IFrame API over postMessage — no library, no network from
`widget.js`). `data.py` stores desired state/commands; the client applies them. Faces, all CLASS-switched
(never inline `display` — an inline style would beat the cinema rules, V2-596):

- **PLAYER**: frame (56.25% ratio), verifiable metadata (channel + published, V2-057), controls, the linear
  text playlist (V2-366: `add` NEVER autoplays; `ended` advances by itself; `close` stops the video and
  keeps the list). Blocked channels (V2-596): the filter lives in the widget's data, applied at every
  NAME-search door and at the suggestions door; an explicit pasted link is an order and is never filtered.
- **HOME** (`hb-yt-homemode`): with nothing loaded the card IS the catalog — thumbnail tiles of the queue,
  plus the **suggestions band** (V2-597, see below). The ⌂/▶ nav button switches views without unmounting
  the iframe.
- **CINEMA** (`hb-cinema` on the card, set by the host): maximized, the video IS the screen; the floating ⤡
  exits. `maximize()` resolves a missing catalog meta LAZILY (a card restored on reload and maximized before
  the catalog fetch answered used to keep its chrome — measured live 2026-09-05).
- **CONNECT** (`hb-yt-connmode`, V2-597): platform icons in the nav row (messaging `.dots` pattern — bright
  = connected → status screen; dimmed = not connected → step wizard). The wizard shows ONE step at a time
  (V2-561 shape) and is ONE step when the build ships its own OAuth client, two when the operator brings his
  own (V2-603); the consent window is opened synchronously on the click and its location filled from the
  action's answer. The voice door is the declared `open_connectors` action writing a timestamped
  `connect_focus` the card consumes once.
  **Today this whole layer is HIDDEN** (V2-603 F2): with no OAuth client anywhere, `service.available()` is
  false and the card renders no platform row, no wizard and no suggestions band, while the three account
  actions decline with one shared sentence. The gate is DERIVED, so it re-appears by itself the day a
  client_id lands — a door that cannot open is worse than no door.

**Anchored to the parent** (operator's rule, 2026-09-05): `.hb-yt` is `width:100%` + `border-box` — the CARD
decides the width in every state (maximize, manual resize, arrange); the default footprint is declared in
`manifest.size` (680), not in the CSS.

## The connector (`connectors/video/`)

The V2-557 family shape, one provider in v1 (YouTube) but a FAMILY by design — per-platform results, never
mixed; adding a provider touches the registry + one client module, zero widget lines.

```
providers.py   typed registry (YouTube: Google OAuth endpoints, tier readonly = youtube.readonly;
               the write tier is deliberately NOT declared until subscription management ships)
oauth.py       PKCE S256, callback served by our own server (/api/video/callback), tokens in
               SecureJsonStore (.meshkore/credentials/video_oauth.json, chmod 600, gitignored);
               a refresh without a refresh_token KEEPS the previous one; granted tier rides with the token
youtube.py     Data API v3 client: subscriptions.list + per-channel recent uploads via the DERIVED
               UU<channel> uploads playlist (saves one channels.list per channel; ~26 quota units of
               10,000/day per full pull)
service.py     the agnostic facade — fail-safe ({"ok": False, "error"}), and a legitimate emptiness
               (an account with zero subscriptions) answers ok + reason, never an error
server_api.py  /api/video/{status,connect,callback,disconnect} — credentials are typed ONCE in the
               settings panel; no widget payload ever carries one (V2-520)
```

`data.py` is in `_STDLIB_EXEMPT` with DEFERRED imports (the catalog pays module import on every prompt).
`view_data` is connector-free: platform rows are CACHED in the widget's store (`platforms` +
`platforms_stale` computed from age — the archivos `needs_refresh` pattern); the card asks for one
`sync_platforms` when stale (local file reads, no provider network).

## Suggestions (`suggest`)

Recent uploads from the connected account's subscriptions, newest first, normalized
(`{videoId,title,channel,published,url}`), blocked channels dropped at this door with the count reported
(V2-414: a silent drop reads as a worse search). **No background refresh, by decision**: the operator's
standing rule is absolute control — the band fills when asked (voice `suggest`, or the band's ↻), never on
a timer. A disconnect empties the band (data that nothing backs must not keep showing).

## The widget's own LIBRARY (`library.py`, V2-604)

Operator's rule: *the widget stores the data, not the connector*. Followed channels, watch history,
preferences and saved lists live in the widget's own store and owe the connector nothing — every test in
node 4.116 runs with it ABSENT, which is also its real state today.

```
channels      [{name, added_at}]                    OUR subscription list, the mirror of blocked_channels
history       [{videoId,title,channel,url,          what was really PLAYED, newest first, capped at 300
               played_at, plays, quality}]
prefs         {min_definition, captions, volume}    the ENFORCEABLE keys, and only those
prefs_notes   [{text, added_at}]                    everything else he asked for, labelled as a note
lists         [{name, items, saved_at}]             saved queues
```

Four things that are easy to get wrong when touching it:

- **The history is ours because we PLAY the video.** It is recorded in the two places playback really
  starts (`_play_pos` and `load`) and nowhere else, so `add`/`search` — which never autoplay (V2-366) —
  never enter it. A replay MOVES the row and bumps `plays` instead of adding a second one. This is the one
  video fact no connector could ever hand us: the YouTube API's watch history has returned empty for every
  account since 2016.
- **Definition is only knowable at the PLAYER.** The results page does not publish it (measured 2026-09-07:
  of ~20 hits only 4K carries a badge at all), so `widget.js` reports `availableQualityLevels` from the
  `infoDelivery` the player already sends, once per video, and `player_quality` checks it against
  `min_definition`. It **warns and never skips**: he asked for THIS video, and an explicit order outranks a
  standing filter — the same line `block_channel` draws for a pasted link. Levels that carry no information
  (`auto`, `default`) produce no verdict at all.
- **An unenforceable preference is a NOTE and says so.** Only `min_definition`, `captions` and `volume` are
  applied; anything else lands in `prefs_notes` and the answer states plainly that it will be honoured by
  judgement, not forced. Storing an unenforceable rule as if it were enforced is the "true sentence about
  the wrong mechanism" failure V2-603 already paid for. `captions` is re-asserted on every video; `volume`
  only when playback starts from nothing, so a standing preference never undoes his last explicit order.
- **The manifest gate follows the delegate.** `widgets/validator.py` reads `apply_action` statically and
  rejects declared actions it cannot find a branch for. It read `data.py` ONLY, so the architecture ratchet
  (pay a growing file by EXTRACTING) and the gate (the branch must be HERE) pulled in opposite directions —
  leaving "one god file per widget" as the only green option. It now follows one level of delegation
  (`library.apply(action, …)` in a sibling module) and still fails closed in both directions.

## Tests

Nodes 4.116 (the library: no connector anywhere, history recorded only by real playback, the quality rule
warns without skipping, an unenforceable preference stays a note) · 5.13 (connector unit) · 5.14 (LIVE roundtrip — skips with enable steps; shape-only assertions, this
repo is public) · 4.4 (contract: intent-not-credentials, filter, ok+reason) · 4.53 (RENDER: one wizard step
at a time, synchronous consent window, the voice door, the band, parent-anchored width).
