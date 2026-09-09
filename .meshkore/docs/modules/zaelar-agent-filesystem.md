# The agent's own filesystem (`library/`) — V2-638

One root the AGENT owns, with a folder per kind of thing, shared by every widget. What a widget downloads is
not that widget's property: a paper the `documento` widget fetched, a track the music widget got, a film the
video widget is streaming — they all live here, and any widget reaches any of it by path.

```
<workspace>/library/
  video/        films and video
  audio/        music and any audio
  documents/    papers, books, PDFs
  images/       pictures
  downloads/    the torrent client's SANDBOX — it writes here and nowhere else
```

## The layout is GENESIS, and the operator overrides it

The factory defaults ship in `nucleo/genesis.json` under `library`; per-install overrides live in
`<workspace>/config/library.json` and are mtime-cached, exactly the two-layer shape V2-633 uses for the style
policy. The operator can rename a folder, move the root, rewrite the structuring guide, or flip the download
policy. `paths.set_overrides()` MERGES — renaming one folder must not silently reset the other four.

A folder name is **one segment**: `_safe_segment` strips separators and dots, so a rename can never relocate
the library (a name containing `../../tmp` would otherwise move the whole tree).

## `resolve()` is a security seam, not a convenience

Every path arriving here is untrusted — a magnet payload, model output, an HTTP query string. `paths.resolve()`
is the ONLY way to turn a relative name into a real path, and it answers `None` for anything outside the root:

- **an absolute path is REFUSED, never reinterpreted.** Stripping a leading slash maps `/etc/passwd` to
  `<library>/etc/passwd` — safe, since it stays inside, but it answers a question nobody asked and hides the
  caller's real (wrong) intent behind a plausible path.
- `..` is refused.
- the check is made against the **resolved** path, which is the only version that catches a symlink planted
  inside the library pointing out of it. A string-prefix check passes that one.

## Only what the browser can play — by default

`formats.py` separates two questions that look like one: what a file **is** (`kind_of` → video/audio/image/
document/other) and whether the **browser** can play it (`browser_playable`). An `.mkv` is a video and belongs
in `video/`; it is also undecodable by every mainstream browser, so it is never chosen for playback.

`allowed(name, keep=False)` is the operator's rule: bring home what the page can play, unless he explicitly
asks to keep the file (the pendrive case). A file that is not playable is still offered — `/api/library/download`
hands it over with any format — because refusing without a way round is how a legitimate file looks broken.

⚠️ This corrected a real defect in V2-637, where `.mkv`/`.avi` were treated as playable video: the torrent
client could pick a file it was structurally unable to show.

## HTTP (`/api/library/*`, loopback)

| Route | What |
|---|---|
| `GET /rules`, `POST /rules` | the structure and the operator's overrides |
| `GET /list?kind=&playable_only=` | the normalized records a widget consumes |
| `GET /summary` | counts and bytes per shelf |
| `GET /stream?path=` | **the one route both players use** — `FileResponse`, so Range/`206` for free; a file the browser cannot decode is refused here (415 + the download url) rather than served as a black rectangle |
| `GET /download?path=` | the file itself, any format, as an attachment |

A still-DOWNLOADING torrent is the other case and has its own piece-aware route in `connectors/torrent` — the
file on disk is full of holes until it completes.

## Who consumes it

- `widgets/youtube/sources.py` — a `local` row plays in a plain `<video>` against `/api/library/stream`.
- `widgets/musica/local_audio.py` — a track whose `uri` is `local:<rel>` plays in an `<audio>` against the
  same route. Mixed playlists (Spotify + YouTube + a local file) need no schema change because of it.
- `connectors/torrent` — writes into `downloads/`, and `service.file_it()` shelves a finished file.

## Cloud vs self-host

Identical. The root is under `nucleo.workspace.root()`, so a cloud Machine's mounted Volume carries it; the
tree is declared in `workspace.SUBDIRS` so a fresh Volume already has the directories, and `COPY library` is
in the Dockerfile (the V2-554 guard caught its absence before it could break a boot).

Tests: node **7.42**.
