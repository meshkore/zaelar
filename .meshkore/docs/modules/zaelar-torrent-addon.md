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
| `widgets/torrent/` | The `Descargas` widget: a MANAGER (see below), never a player. Its declared actions ARE the skills (V2-544) — the FlashBrain drives them through the generic `widget_data` tool, no bespoke model tool. |
| `nucleo/torrent_router.py` | Hands a Descargas row to the widget that can actually play it (see below). |

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

## The Descargas widget is a MANAGER, not a player (redesign)

The operator's brief: it has to look like a real torrent client. Two lists, like any client — files that are
part of the SEEDS (finished, still sharing back) on one side, files still DOWNLOADING (or finished but not
yet reannounced as seeding) on the other. Per row: play, save, remove-the-torrent-and-the-file. One download
alone renders as a single "hero" card (the original single-download layout, kept because it read well);
several switch to a compact row list — never one download claiming the whole screen regardless of how many
are running.

`widgets/torrent/data.py::view_data()` builds both lists FRESH from `connectors.torrent.service.active()` on
every render — no private "my downloads" bookkeeping. The client is a SYSTEM tool (see below): a magnet
started from this widget, from `youtube`'s own `play_torrent`, or by voice, all land on the one shelf every
caller reads. `session.status()` now also reports `file_name`/`kind`/`playable` (`library.formats` decides,
never a second copy of its lists) and `group` (`"seed"` once libtorrent's own state says `seeding`, `
"download"` otherwise) — the exact split the two lists render.

**Playing routes to whichever widget owns that surface — never inline here.** A playable video row's ▶ asks
`nucleo/torrent_router.py::route_video(rid, title)`, which calls `youtube`'s `play_torrent` action WITH the
existing id (`widgets/youtube/sources.py::play_torrent` grew an `id=` parameter for exactly this: adopt the
SAME session handle via `item_from_torrent`, no re-search, no new download) and raises the card
(`voice.observer.emit("widget","show",...)`). A finished, playable audio row's ▶ files it onto its shelf
first (`service.file_it`, which now also RETIRES the handle — see below) then hands the library-relative path
to `musica`'s `play_local`. Either way the OTHER exclusive-audio widget is asked to pause first, best-effort,
mirroring `widgets/producers.py`'s "one speaker" rule without needing its async exclusivity machinery (this
call may not have a running event loop under it).

This crosses widget boundaries on purpose, and it lives in `nucleo/`, never inside `widgets/torrent/data.py`
itself: "widgets are dumb and never talk to each other" (`widgets/AGENTS.md`) means a widget's OWN
`apply_action` must not reach into a sibling's store. `nucleo/torrent_router.py` is the same layer
`nucleo/docsheet.py` already uses for an analogous hand-off (opening `documento` bound to a worker's errand)
— an orchestrator that is ALLOWED to know several widgets' shapes, called by a widget's `data.py` instead of
that widget importing its sibling directly.

`service.file_it()` used to just move the file and leave the torrent handle alone — which meant a completed
download that got filed kept a handle in `active()` pointing at a path that no longer existed (the file was
gone from `library/downloads/`), so the piece-aware stream route would serve nothing for it ever again and it
would sit in the seeds list forever, dead. It now calls `session.remove(rid, delete_files=False)` right after
a successful move — the file already left the sandbox, there is nothing left there to delete.

A row's DELETE asks a real "¿Eliminar y borrar el fichero? Sí / Cancelar" inline before calling `remove`
(`agenda`'s own two-step click-to-confirm pattern, `state.confirmDel`) — the manifest's `"confirm":true` on
that action only gates the FlashBrain's own dispatch of it; a raw UI button click goes through the plain
`/widgets/{id}/action` route and bypasses that gate entirely, so a destructive button needs its own confirm
step in the widget itself.

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

The manager redesign (multiple rows, the seed/download split, the `open`→`nucleo/torrent_router.py`→
`youtube`/`musica` hand-off, the `save`→`file_it`→handle-retirement path) is covered by unit tests against a
faked connector and a Chromium-rendered phone fixture — never against a real libtorrent session or a real
engine. Needs an engine restart plus a real magnet to confirm end to end: (1) two-plus concurrent downloads
actually render as a list, not a hero card each; (2) a video row's ▶ genuinely opens `youtube` playing that
torrent's own stream while it is still filling; (3) a finished audio row's ▶ genuinely files it and starts it
in `musica`; (4) removing a row actually deletes the file on disk.
