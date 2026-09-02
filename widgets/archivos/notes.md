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
