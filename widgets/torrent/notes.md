# torrent — Descargas (V2-637)

Plays a video obtained by BitTorrent inside the agent, while it downloads. Backed by
`connectors/torrent/` (libtorrent, pure-Python wheel — nothing installed on the host). The search is a
MeshKore network agent, not this widget; here we download the magnet and stream it.

- **Actions ARE the skills** (V2-544): `search {query}` (mesh → magnet → download), `play {magnet}`,
  `poll` (refresh progress), `stop` (cancel + delete). Driven via the generic `widget_data` tool.
- `data.py` reaches `connectors.torrent.service` (deferred import; in `validator._STDLIB_EXEMPT`).
- `widget.js` builds the `<video>` ONCE and only UPDATES it on re-render (the V2-124/4.19 rule); the
  player appears only when `stream_url` is set (i.e. `streamable`), never over an empty file.
- Streaming is HTTP Range from `/api/torrent/stream/{id}`, served while the file still grows.

Full mechanism: `.meshkore/docs/modules/zaelar-torrent-addon.md`. Tests: node 5.22.
