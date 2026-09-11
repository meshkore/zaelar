# archivos — running log

- **2026-09-02 · V2-557 · created.** Operator's order: a connector to their cloud files (Google Drive or
  OneDrive) plus «a file-navigation widget as close as possible to the ones that exist», drivable with the
  mouse AND by voice («get me into this folder, find me a file that has this data, list me this and that»).
- **GENERIC on purpose, explicitly asked for**: the provider lives entirely behind
  `connectors.files.service`, which returns ONE normalized entry shape. Nothing in this widget knows what
  Drive or Graph call things — a third provider is a client module over there and zero lines here. Do NOT
  add a provider-specific branch to `data.py` or `widget.js`; if something cannot be expressed in the
  normalized entry, the entry grows, not this widget.
- **`view_data` never touches the network.** It is called on every render and again on every SSE push, so a
  fetch there is an HTTP round trip per repaint. All network lives in `apply_action`. The card asks for a
  listing ONCE on mount when the cache is stale (`needs_refresh`), guarded by a flag on the DOM node — a
  module-level guard would make the first refresh the last one this widget ever asks for.
- **Foreground-only, decided not defaulted (V2-034).** No `tick`: polling somebody's cloud storage burns API
  quota to answer a question nobody asked, and there is no proactive fact here worth speaking.
- **A non-browsable permission is NOT an empty drive.** Google's narrow tier (`drive.file`) answers 200 with
  an empty array, which reads exactly like «this folder is empty». The service layer returns `ok` plus a
  `reason`, and the card prints the reason. Never collapse those two states.
- **Every name on screen is untrusted** — it comes from somebody's cloud. `textContent` only, never
  `innerHTML`. A file called `<img onerror=…>` is a legal file name in every provider we speak to.
- **The connect wizard stays INSIDE the card** (house rule: a widget's sub-flow never becomes a separate
  window). It also exists in ⚙ → Conectores; both read the same catalog so they cannot drift.
- **No cross-widget calls.** `open_file` hands back the file's metadata and `web_url`; whether that becomes a
  document on the canvas or a page in the browser is the BRAIN's call. Widgets are dumb and brain-mediated.
- **`size` is None, never 0**, for anything with no size (a folder, a native Google doc). «0 B» next to a real
  document is a statement, and it is false.
- **2026-09-10 · V2-658 · redesign: ONE file manager, LOCAL library first.** Operator's order: this widget
  should work like the rest — a header icon row for the storage (this device, Drive, OneDrive, "y los que
  vengan"), the AGENT'S OWN library (`library/`, V2-638) as the full-featured default with rename/copy/delete/
  open, a cloud connector alongside it that offers only what it can (today: navigate + search + open — no
  write API). Mirrors `youtube`'s connector shelf and `mensajeria`'s platform-icon header rather than inventing
  a third pattern. `provider` defaults to `"local"` now, not `""` — local needs no connection, so `connected`
  reads True the instant the provider is local. `DB_VERSION` 1→2 migrates a stale cloud-only store onto the
  new default.
- **The five shelves are the "folders" — and there is no deeper nesting, deliberately.** `library/index.py`'s
  `listing(kind=…)` classifies a file by its EXTENSION across the whole tree, not by which physical folder it
  sits in (V2-638's own design: the shelf a new file lands on is where it is FILED, not a directory the
  operator can create subfolders inside). So a real cut/paste MOVE across shelves would misfile a file by
  location while `listing()` kept finding it anyway by extension — a worse file manager than none. `copy_file`
  (an in-place duplicate) is the operation that stays honest under that model; a cross-shelf move is not
  offered. If the library ever grows real nested folders, this is the file to revisit first.
- **Opening a file routes through `nucleo/library_router.py`**, the sanctioned orchestrator layer (same shape
  as `nucleo/torrent_router.py`/`nucleo/docsheet.py`) — `data.py` never imports `widgets.youtube`/
  `widgets.musica` directly. A playable video/audio hands off and the target card raises itself; a playable
  image/document previews INSIDE this card (a small built-in lightbox — `<img>`/`<iframe src=…>` against this
  widget's own `/api/library/stream` route, never another widget's store); anything else refuses with the
  reason and a download link (`library/formats.py::refusal()` — the pendrive escape hatch).
- **Rename/copy/delete are LOCAL ONLY.** A cloud row's per-file actions are just the existing "open the web
  link" — the widget does not grey out buttons the connector cannot honour, it simply does not draw them,
  matching the operator's own framing: the connector's limit, never this widget's.
- **The provider icon row is a NEW sync path** (`sync_providers`, mirrors `youtube`'s `sync_platforms`,
  V2-597): `view_data` must stay network-free, but the header needs to know about Drive/OneDrive icons before
  the operator ever opens the connect wizard, so the card asks once when `providers_stale`, same shape as
  `needs_refresh`.
- **Rename/delete UI state lives on the mount node (`root._arxUi`), not the store** — a delete confirmation or
  an in-progress rename is per-viewer chrome, not a fact the brain or another tab needs to see. Flipping it
  forces a repaint the only way available (`act("refresh", {})`, a cheap round-trip that pushes over SSE) since
  the host only re-renders on a server push.
- **2026-09-11 · design pass: the root IS the mount node, no wrapper div — and the header is ONE row.**
  Operator's screenshot: the home screen's shelf tiles filled barely 40% of a maximized card's width, the
  provider chip sat alone with a huge dead gap before ⚙, and the tiles read as borderless in his dark theme.
  Root cause: `render()` created a CHILD `<div class="arx">` and appended it to the passed `root` instead of
  setting `root.className` directly — `results`/`documento`/`youtube` all set the class on the element they
  are GIVEN (V2-615's own convention), and the one test that exists for this
  (`test_widget_roots_fill_a_wide_desktop_card.py`) measures `#host` itself, which stayed a plain full-width
  div regardless of what a CHILD did — so the bug was invisible to that guard. Fixed: `root.className = "arx"`,
  no wrapper, plus an explicit `width:100%;box-sizing:border-box` on `.arx` (belt and suspenders, matching
  `youtube`'s own `.hb-yt` rule). The old two-row chrome (a provider-chip row, then a separate breadcrumb+tools
  row) is now ONE `.arx-bar`: chips · divider · breadcrumb · tools, so there is no empty band between them —
  see `header()`. Shelf tiles and list rows gained a background + shadow distinct from the new `.arx-body`
  panel background (`--hb-bg` tiles over a `--hb-bg-soft` body), so the content area reads as one bounded
  surface instead of bleeding into the card. Icon badges (chips, shelves) use `display:grid;place-items:center`
  — flex centering plus emoji line-height metrics was reading as visibly off-center.
- **A card's header MAXIMIZES on a DOUBLE-click — corrected live, in front of the operator.** First cut bound
  a single tap to maximize; he tried it and corrected immediately: *"he dicho doble clic, no uno solo... me
  pide solo un clic y de golpe ya se maximiza"*. `.hb-head` (`frontend/app/widgets/desktop.js`) is already the
  drag handle (V2-608 F6) and `maximize()` is already a toggle that saves/restores geometry (V2-600/V2-609) —
  `_dragHandle`'s tap-vs-drag distinction (`moved` flag, 4px threshold) now wires a `dblclick` listener on
  `.hb-head` (guarded against landing on the header's own buttons) straight to `this.maximize(id)`. A single
  tap stays a no-op in BOTH directions — it is also the resting state of a drag gesture.
- **Maximizing now covers the FULL viewport, for every widget — except the bottom system rail.** Same
  session, same screenshot: a maximized `archivos` card still sat under the top icon cluster (Reset/⚙/☾/…).
  V2-596/V2-600 already built exactly this coverage (`.hb-cinema`, a floating `.hb-cinexit` exit button) but
  reserved it for `fullscreen:"native"` widgets (video) ONLY, and deliberately covers the rail too there
  (full immersion). `maximize()` now applies a SIBLING class, `.hb-fullwide`, to every other widget: same
  full-viewport `position:fixed` treatment, own hidden chrome, own visible `.hb-cinexit` — but its stage
  z-index (9001) sits below the rail's (9002, V2-623) on purpose, so the orb/mic/widget-switcher stay
  reachable while a normal widget fills the screen. Video's `.hb-cinema` is untouched.
- **A local file that cannot play in the browser is NEVER downloaded by a click — it is REVEALED.**
  Operator, live: double-clicking an unplayable `.mkv` in the Descargas shelf downloaded a SECOND copy into
  his Mac's own `~/Downloads`, next to the one already sitting in Zaelar's own library on that SAME disk —
  "eso es ineficiente". `_same_machine()` (`nucleo.cloud_account.is_cloud_account()`, inverted) tells apart
  self-host (the engine process IS the operator's own computer — shelling out to `open -R`/`explorer /select,`/
  `xdg-open` there is no bigger a privilege than the library writes this widget already does) from a cloud
  Machine (no local disk of the operator's exists to reveal — the gesture is hidden entirely there, and the
  explicit ⬇ stays the only, correct, way to get a copy onto HIS computer). New action `reveal_local_file`
  (self-host + local provider only) shells out best-effort and always returns the resolved absolute path, shown
  inline with a Copiar button — the honest fallback for a desktop-less self-host. Every local row now carries
  `same_machine`; `rowActions()` shows 📁 (reveal) only when true, and ⬇ (explicit download, never the primary
  click) whenever `download_url` exists — both, never neither, for a self-hosted unplayable file.
- **REAL BUG FOUND while chasing "the ▶ button does nothing": `src:"user"` on a cross-widget `widget/show`
  emit is an ECHO marker, not a free-text label — it silently DISCARDS the event.** `frontend/app/services/
  sse.js` treats any `widget/show` with `src==="user"` as something the browser's OWN click handler already
  applied (the one legitimate case: `server/voice_api.py`'s periodic canvas-diff AUDIT, reporting what the
  operator's client already did) and skips calling `desktop.show()` — so `nucleo/library_router.py`'s (and,
  copied from it, `nucleo/torrent_router.py`'s) `_show()` helper, which used `src:"user"` for a genuine
  SERVER-initiated hand-off, silently never opened the player card. Every other emitter in the codebase names
  WHO is driving the show (`"flash"`, `f"worker:{tid}"`, `f"wall:{task_id}"`) — never `"user"`. Fixed in both
  router modules to `src:"widget"`. This means the Descargas widget's own ▶ button has been silently broken
  since V2-637/V2-638 shipped, discovered only now because the archivos redesign hit the exact same class of
  hand-off. ⚠️ **NOT verified live end-to-end** (needs an engine restart + a real click) — verified only that
  the emit call itself now carries the right `src`, and that `sse.js`'s `_eco` check reads exactly that field.
- **2026-09-11 · V2-663 · navigation clarity — a sidebar, ONE search field, a real breadcrumb, and an exit
  from the connect screen.** Operator's live screenshots: he double-clicked an unplayable `.mkv` (correctly
  offered reveal-vs-download, V2-658), then typed a search — and reported *"no sé en qué carpeta estoy, no sé
  cómo volver atrás"*, plus *"hay dos campos"* pointing at the breadcrumb's own `«Resultados de X»` pill sitting
  right next to the actual search input showing the SAME query. A second screenshot showed the connect
  wizard (`panel:"connect"`) with no header at all — just provider cards and a "← Volver" button at the very
  bottom, no way out without scrolling to find it.
  - **The duplicate search box is gone.** `crumbsRow()` no longer prints a `«Resultados de X»` span — the
    breadcrumb always shows the REAL place (home, disabled when `trail` is empty, which it is for a local
    search — an honest "this searched everywhere", not a fake location). The query lives in exactly ONE
    place, the `.arx-find` input, with its clear (✕) and a result-count tag (`.arx-tag`, "N resultados") now
    living right next to the breadcrumb instead of repeating the text he already sees in the box.
  - **A long cloud trail collapses.** `crumbsRow()` keeps the deepest two steps and an "…" for the rest past
    that (`ui.crumbsExpanded`, the same per-mount UI-state pattern rename/delete already use) — his own
    "if there are 200 folders, don't print 200 folders" spec. The one-level-deep LOCAL library never has a
    trail long enough to trigger it (`_relist_local` only ever writes one entry) — this is a cloud-only path.
  - **A SIDEBAR, Finder/Explorer-shaped, at a wide card** (`ensureTierObserver`, `root.dataset.tier` ∈
    s|m|l off a `ResizeObserver` on the mount node — measures the CARD's own box, not the viewport, since a
    card resizes independently of the window): past ~900px, `.arx-side` lists the five local shelves plus
    every cloud service with a live connected/off dot, each one a second, always-visible way to the same
    places the header chips already reach — additive, not a replacement, so the header chips (and every test
    that reads them) are untouched. Below that width it is not rendered at all; a phone-width card never pays
    for it.
  - **Progressive columns, CSS-only so a resize needs no re-render.** `.arx-col-date`/`.arx-col-loc` are
    always IN the DOM (`display:none` by default, shown at `data-tier="m"`/`"l"`) rather than conditionally
    built in JS — `ensureTierObserver`'s callback only flips the `data-tier` attribute, it never calls
    `render()` again, so a column that JS decided not to build would stay missing until the next real
    repaint. The location column (which shelf a MIXED search hit lives on — `data.py`'s new `shelf` field on
    a local row, the reverse of `_FMT_KIND`) only shows during a search at the wide tier; a plain single-shelf
    folder already says its shelf in the breadcrumb, so repeating it per row there would be noise.
  - **The connect screen finally has an exit that doesn't need scrolling.** `connectPanel()` is now its own
    small screen: a top bar with the title and a `✕` (`.arx-cxclose`), the original "← Volver al explorador"
    kept at the bottom too — belt and braces, since he landed here from two different places (the ⚙ tool and
    now, additionally, every sidebar cloud row and every unconnected header chip).
  - **Provider chip text is UNCHANGED on purpose** — the existing render test asserts `chip.textContent`
    equals the bare letter/emoji, so richer labelling happens through the NEW sidebar (which has room for a
    full name) rather than by growing the chip's own text, which would have broken every `pchips` assertion
    for a cosmetic gain the sidebar already delivers.
  - Node **4.156** (`test_archivos_render.py`, 5 new cases: sidebar tier gating with real shelf/service names,
    the single-search-field assertion incl. "no `Resultados` crumb", the mixed-search shelf column shown only
    at the wide tier, the trail-collapse/no-collapse pair, the connect screen's close visibility). Two disarms
    verified red (tier threshold, the close button's existence) before shipping. `make test-widgets` 15/15
    (golden untouched — `view_data()`'s own keys did not change, only a new field on already-existing local
    rows). **NOT verified live** — needs an engine restart and the operator's own eyes on the real card.
