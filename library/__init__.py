"""The agent's OWN filesystem (V2-638) — one root, a folder per kind, shared by every widget.

Operator's directive: what Zaelar downloads is not the property of whichever widget fetched it. A paper the
`documento` widget pulled, a track the music widget got, a film the video widget is streaming — they all live
in ONE tree with a sensible structure, and any widget can reach any of it by path. The layout ships in
`nucleo/genesis.json` and the operator overrides it by saying so (`<workspace>/config/library.json`).

  · `paths.py`   — the layout (genesis + overrides) and `resolve()`, the ONE boundary-safe door.
  · `formats.py` — what a file IS, and whether the browser can play it (the default download policy).
  · `index.py`   — the normalized record a widget consumes: `url`, `playable`, `kind`, `size`.
  · `server_api.py` — `/api/library/*`, including the single stream route both players share.
"""
