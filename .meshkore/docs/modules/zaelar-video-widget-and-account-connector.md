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

**THE NUMBERED BAND IS A PROMISE.** «el tercero» only means anything while row three stays row three,
so a SEARCH is a question and asking it twice does not change the answer: the same query over the band
already on screen is answered (`unchanged: True`), not re-fetched and not renumbered. The operator read
the defect out loud — «Bueno, ponme el vídeo dos, que los has cambiado» (V2-756). One bound: a band
holding something he has since refused (a video that failed to play is blocklisted) is NOT the same
question, and the search is re-run so the refused stays out.

**AND THE QUEUE TAKES SEVERAL.** `remove` accepts `items="4,5,6"` as well as a single `item`, the shape
`add_results` has had since V2-632. Without it «bórrame los tres últimos» deleted ONE row — the rule is
one action per turn, so a plural the manifest cannot express is a capability that does not exist, and
the paid verdict reached instead for `clear_list`, which empties the whole queue.

**WHO MOVES THE FACE.** `selectTab` is the card's ONE navigation transition (V2-626) and `goto_tab` — a
SEQUENCE, so the same face can be asked for twice — is the only way in from outside it (V2-742). Three
writers, and the distinction between them is the whole of V2-755:

- the declared `show_tab` action, for «vuelve al catálogo» (its faces' ALIASES live in the manifest payload
  and `widgets/enums.py` is the only parser, so the model reads the same words the widget accepts, V2-754);
- **an ORDER to play** (`load`, `play_result`, `play_item`, an explicit `next`/`previous`) writes
  `goto_tab → player`, because «ponme el sexto» means watching it. The card's own transition cannot do this:
  it sees a video ARRIVING on an empty card, not one being SWAPPED, so an order given from the catalog ran
  twice with nothing on screen changing (live session 665e666a);
- **the automatic advance when a video ends writes nothing** — he reads the queue while one plays, and
  yanking his view on a track change is the same defect with the sign flipped.
- **a SEARCH** writes `goto_tab → inicio` (V2-757), for the mirror reason: a search arriving means looking
  at what it found. With Ronaldinho playing he asked for videos of the moon landing, six numbered results
  landed on the dashboard, the card stayed on the player, and he spent three turns saying «yo no veo el
  catálogo, solo veo el vídeo de Ronaldinho» while the engine insisted they were there. The player is NOT
  touched — whatever is sounding keeps sounding (V2-366). The «that question is already answered» branch of
  V2-756 writes it too: nothing is re-run, but the reason he asks twice is almost always that he cannot see
  the answer.

And the card refuses one stored order: the player's face with no video in it. `goto_tab` is persisted and
the consumed sequence is module-lived, so a reload replays the last order — onto a blank Reproductor, which
is the dead end V2-753 exists to prevent.

⚠️ **A FORK OF THIS CARD SHADOWS IT, AND IT IS GITIGNORED** (V2-757). `widgets/_user/youtube/` wins over
`widgets/youtube/` in the catalogue, in `identify`, in the `widget.js` that is served and in the Python
imports (`widgets/paths.roots()` puts the generated root first and `_sync_import_path` applies it to the
package). Measured on 2026-09-23: a Brain Worker forked this card and rewrote 249 lines of its CSS, so for
several hours the operator's engine was running a copy — and **V2-755 and V2-756 were inert on his machine**
while `git status` stayed clean. Before diagnosing anything about this widget, ask which FILE is running.

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
