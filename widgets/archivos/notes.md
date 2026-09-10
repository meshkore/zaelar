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
