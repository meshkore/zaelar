"""Embedded BitTorrent client — download a magnet and STREAM its video into the player (V2-637).

The mesh already hands us a magnet (a torrent-search agent in the Oracle answers «find a torrent of X»).
What was missing is the other half the operator asked for: a client that turns that magnet into something the
`torrent` widget can PLAY, inside the engine, with no external app and nothing installed on the host — the same
promise as the embedded browser (`navegador`). The whole client is one pure-Python wheel (`libtorrent`), so it
ships in our package and runs identically on a self-host machine and on a cloud Machine.

The layers, agnostic to the rest of the system exactly like `connectors/video`:
  · `session.py`  — the libtorrent session as a LAZY process singleton (one for the whole engine), plus the
                    sequential-download + streaming plumbing. The only file that imports libtorrent.
  · `service.py`  — the fail-safe facade the widget and the API call. Never raises to a caller; `available()`
                    is DERIVED from whether the wheel imported, never a hand-set flag.
  · `server_api.py` — `/api/torrent/*`, the HTTP Range endpoint that streams the growing file to a `<video>`.
"""
