# The embedded torrent add-on (`connectors/torrent/` + `widgets/torrent/`) — V2-637

An add-on that turns a magnet link into a video playing **inside** the agent, while it downloads — the same
promise as the embedded browser (`navegador`): a real client, running in the engine process, with **nothing
installed on the host**. The whole BitTorrent engine is one pure-Python wheel (`libtorrent`, the qBittorrent
core), so it ships in our package and behaves identically on a self-host machine and on a cloud Machine.

## What is ours and what is the network's

The **search is not here.** A torrent-search agent lives in the MeshKore Oracle; asked «find a torrent of X»
it queries indexers and returns an active magnet. This module is the other half — the **client** that takes a
magnet, downloads it, and streams it. `connectors/torrent/search.py` goes through `mesh_agents.serve` like any
other errand (free agents only, a 402 is a fact never paid, «nobody does this» comes back as a speakable
reason) and pulls the magnet out of whatever shape the agent answered with.

## The layers (agnostic, like `connectors/video`)

| File | Role |
|---|---|
| `connectors/torrent/session.py` | The **only** file that imports libtorrent. The session is a LAZY process singleton (built on first use, never in the ASGI lifespan — which runs twice). Adds a magnet, resolves metadata, picks the **largest playable file**, sequential-downloads only that file, and exposes `iter_range` for streaming. |
| `connectors/torrent/search.py` | Magnet lookup through the MeshKore network. |
| `connectors/torrent/service.py` | The fail-safe facade the widget and API call. Never raises. `available()` is **DERIVED** from the wheel importing — no hand-set flag; a machine without the wheel simply hides the connector. |
| `connectors/torrent/server_api.py` | `/api/torrent/*`, loopback. The one non-trivial endpoint is `GET /api/torrent/stream/{id}`. |
| `widgets/torrent/` | The `Descargas` widget: progress while downloading, a `<video>` once streamable. Its declared actions ARE the skills (V2-544) — the FlashBrain drives them through the generic `widget_data` tool, no bespoke model tool. |

## Streaming a file that is still downloading

Starlette's `FileResponse` stats a file once and trusts that size — useless for a file that is still growing.
So `server_api.stream` hand-rolls a `206`: it parses the browser's `Range:` header, reports `Content-Range`
against the **full** file size (what a `<video>` needs to seek), and streams the slice through
`session.iter_range`. `iter_range` reads from **disk**, not through libtorrent's read-piece alert queue: a
completed piece is checked and flushed to the file by default storage, so the handler prioritizes the pieces
it is about to serve (`set_piece_deadline`), waits for `have_piece`, then reads the byte slice like any file.
Sequential download plus a per-file priority keeps the front of the chosen video arriving first, which is what
makes «play while it downloads» work. A chunk that never arrives raises inside the generator and **closes the
stream** — a browser re-requests a Range far better than it survives a socket that hangs forever.

The `streamable` gate (metadata present + the file's first ~4 MB of pieces down) is the only thing the widget
waits on before showing the player; until then it shows progress, never a dead `<video>`.

## It is a SYSTEM tool, not one widget's property (V2-638)

The client downloads into **`library/downloads/`** — its sandbox inside the agent's own filesystem — and
writes nowhere else. Filing a finished file onto its shelf (`video/`, `audio/`, `documents/`) is OUR move
afterwards (`service.file_it`), which is what keeps the client's own reach confined to one directory.

`want` says which shelf the caller came for (`video` / `audio` / `document`, `media` for either of the first
two, `any`), so the SAME client serves the video widget, the music widget and a document fetch. `keep` lifts
the browser-playable default for the operator's explicit «I want the file itself» case.

**The operator's switch**: `config/connectors.json` → `torrent.enabled`, default ON. It needs no credential
and no account, so defaulting it off would just make the feature invisible; but it is the one connector that
can saturate a line, so someone on a metered or shared connection must be able to stop it outright.
`service.available()` requires BOTH the wheel and the switch.

## Cloud vs self-host

Identical — `library/` lives under the workspace root, so a cloud Machine's Volume carries it unchanged and
the tree is declared in `workspace.SUBDIRS`. `available()` is the only difference, and only on a hypothetical
machine that shipped without the wheel — there the whole feature is off, not broken.

## Boundaries kept (the V2-557 rules)

- `widget.js` never touches the network — the `<video>` loads its own `src` through the browser's own media
  pipeline, pointed at our loopback route.
- `data.py` reaches its connector (in `_STDLIB_EXEMPT`, deferred import) — it IS a connector surface, like
  `archivos`/`youtube`/`fotos`.
- The voice transports intent, never a credential — this connector needs none.

## What is NOT verified live

The metadata-resolution path is proven live (a public-domain magnet resolved its torrent info in ~4 s). The
end-to-end **byte streaming** of a real payload into the player is not exercised in the test suite (a unit test
opens no session and reaches no network); the arithmetic, the `streamable` gate and the fail-safe facade are.
Nodes **5.22** and **7.42**.
